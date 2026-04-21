//=============================================================================
// Module: stdp_engine_v2
// Description: STDP权重更新引擎v2 - 集成主动遗忘机制
//              核心洞察: 遗忘是STDP不强化时的自然结果
// Author: Luna Project
// Date: 2026-03-24
//=============================================================================

`timescale 1ns / 1ps

module stdp_engine_v2 #(
    parameter N_NEURONS = 128,
    parameter DATA_WIDTH = 16,          // Q8.8定点数
    parameter TIME_WIDTH = 32,          // 微秒
    parameter WEIGHT_ADDR_WIDTH = 14,   // log2(128*128)
    parameter FORGET_LUT_SIZE = 256     // 遗忘LUT大小
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     ce,
    
    // 配置接口
    input  wire [DATA_WIDTH-1:0]    cfg_A_plus,       // LTP幅度
    input  wire [DATA_WIDTH-1:0]    cfg_A_minus,      // LTD幅度
    input  wire [15:0]              cfg_tau_plus,     // LTP时间常数
    input  wire [15:0]              cfg_tau_minus,    // LTD时间常数
    input  wire [15:0]              cfg_max_dt,       // 最大STDP窗口
    input  wire [15:0]              cfg_tau_forget,   // 遗忘时间常数(新增)
    input  wire [DATA_WIDTH-1:0]    cfg_forget_thresh,// 遗忘剪枝阈值(新增)
    
    // 前脉冲输入
    input  wire                     pre_valid,
    input  wire [6:0]               pre_neuron_id,
    input  wire [TIME_WIDTH-1:0]    pre_timestamp,
    output wire                     pre_ready,
    
    // 后脉冲输入
    input  wire                     post_valid,
    input  wire [6:0]               post_neuron_id,
    input  wire [TIME_WIDTH-1:0]    post_timestamp,
    output wire                     post_ready,
    
    // 权重存储接口 (BRAM)
    output reg                      weight_we,
    output reg [WEIGHT_ADDR_WIDTH-1:0] weight_addr,
    output reg [DATA_WIDTH-1:0]     weight_wdata,
    input  wire [DATA_WIDTH-1:0]    weight_rdata,
    
    // 权重更新输出
    output reg                      update_valid,
    output reg [WEIGHT_ADDR_WIDTH-1:0] update_addr,
    output reg signed [DATA_WIDTH-1:0] update_delta,
    
    // 遗忘统计 (调试)
    output reg [31:0]               forget_count,     // 遗忘事件计数
    output reg [31:0]               prune_count       // 剪枝事件计数
);

    //=========================================================================
    // STDP查找表 (LUT-based，避免实时指数计算)
    //=========================================================================
    
    // 预计算的STDP窗口: 256点，覆盖 ±cfg_max_dt
    // 索引: 0-127 = LTP (dt > 0), 128-255 = LTD (dt < 0)
    reg signed [DATA_WIDTH-1:0] stdp_lut [0:255];
    
    // 预计算的遗忘衰减LUT: exp(-t/tau_forget)
    // 输入: 时间差(0-255对应0-10tau), 输出: 衰减因子(0-1, Q8.8)
    reg [DATA_WIDTH-1:0] forget_lut [0:FORGET_LUT_SIZE-1];
    
    // 初始化LUT (在综合时计算)
    integer lut_i;
    initial begin
        // STDP LUT初始化
        for (lut_i = 0; lut_i < 256; lut_i = lut_i + 1) begin
            if (lut_i < 128) begin
                // LTP: A+ * exp(-dt/tau+)
                // 简化: 线性衰减
                stdp_lut[lut_i] = (cfg_A_plus * (128 - lut_i)) >>> 7;
            end else begin
                // LTD: A- * exp(dt/tau-)
                stdp_lut[lut_i] = -(cfg_A_minus * (lut_i - 128)) >>> 7;
            end
        end
        
        // 遗忘LUT初始化: exp(-x) where x = i/256 * 10
        // 即覆盖 0 到 10*tau_forget 的时间范围
        for (lut_i = 0; lut_i < FORGET_LUT_SIZE; lut_i = lut_i + 1) begin
            // 泰勒展开近似: exp(-x) ≈ 1 - x + x^2/2 - x^3/6
            // x = lut_i / 25.6 (使得lut_i=256对应x=10)
            real x;
            real exp_val;
            x = lut_i * 10.0 / FORGET_LUT_SIZE;
            exp_val = 1.0 - x + (x*x)/2.0 - (x*x*x)/6.0;
            if (exp_val < 0) exp_val = 0;
            forget_lut[lut_i] = int(exp_val * 256);
        end
    end
    
    //=========================================================================
    // 权重元数据存储 (用于遗忘机制)
    //=========================================================================
    
    // 每个权重记录上次更新时间
    // 使用简单方案: 只记录最近更新的N个权重的时间戳
    // 完整方案需要外部BRAM存储所有时间戳
    reg [TIME_WIDTH-1:0] weight_last_update [0:1023];  // 最近1024个活跃权重
    reg [WEIGHT_ADDR_WIDTH-1:0] weight_addr_map [0:1023]; // 地址映射
    reg [9:0] weight_meta_wr_ptr;
    reg [9:0] weight_meta_rd_ptr;
    
    //=========================================================================
    // 脉冲历史FIFO (最近64个脉冲)
    //=========================================================================
    
    localparam HISTORY_DEPTH = 64;
    localparam HISTORY_ADDR_WIDTH = 6;
    
    reg [6:0] history_neuron [0:HISTORY_DEPTH-1];
    reg [TIME_WIDTH-1:0] history_time [0:HISTORY_DEPTH-1];
    reg history_is_post [0:HISTORY_DEPTH-1];
    
    reg [HISTORY_ADDR_WIDTH-1:0] history_wr_ptr;
    reg [HISTORY_ADDR_WIDTH-1:0] history_rd_ptr;
    reg [HISTORY_ADDR_WIDTH:0] history_count;
    
    wire history_full = (history_count >= HISTORY_DEPTH);
    wire history_empty = (history_count == 0);
    
    //=========================================================================
    // 状态机
    //=========================================================================
    
    localparam IDLE = 4'b0000;
    localparam RECORD_PRE = 4'b0001;
    localparam RECORD_POST = 4'b0010;
    localparam PAIR_SEARCH = 4'b0011;
    localparam COMPUTE = 4'b0100;
    localparam APPLY_FORGET = 4'b0101;  // 新增: 应用遗忘
    localparam UPDATE = 4'b0110;
    localparam CHECK_PRUNE = 4'b0111;   // 新增: 检查剪枝
    localparam OUTPUT = 4'b1000;
    
    reg [3:0] state;
    reg [HISTORY_ADDR_WIDTH-1:0] search_ptr;
    reg found_pair;
    
    reg [6:0] current_pre_id;
    reg [6:0] current_post_id;
    reg [TIME_WIDTH-1:0] current_pre_time;
    reg [TIME_WIDTH-1:0] current_post_time;
    
    reg signed [TIME_WIDTH-1:0] dt;
    reg [7:0] lut_index;
    reg signed [DATA_WIDTH-1:0] delta_w;
    
    // 遗忘相关
    reg [TIME_WIDTH-1:0] time_since_update;
    reg [DATA_WIDTH-1:0] forget_factor;
    reg [DATA_WIDTH-1:0] decayed_weight;
    reg [9:0] forget_lut_idx;
    
    integer i;
    
    //=========================================================================
    // 握手信号
    //=========================================================================
    
    assign pre_ready = !history_full;
    assign post_ready = !history_full;
    
    //=========================================================================
    // 查找权重元数据
    //=========================================================================
    
    function [9:0] find_weight_meta_index;
        input [WEIGHT_ADDR_WIDTH-1:0] addr;
        reg found;
        reg [9:0] idx;
        begin
            found = 0;
            idx = 0;
            for (i = 0; i < 1024; i = i + 1) begin
                if (!found && weight_addr_map[i] == addr) begin
                    found = 1;
                    idx = i[9:0];
                end
            end
            find_weight_meta_index = idx;
        end
    endfunction
    
    //=========================================================================
    // 主状态机
    //=========================================================================
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            history_wr_ptr <= 0;
            history_rd_ptr <= 0;
            history_count <= 0;
            weight_meta_wr_ptr <= 0;
            weight_meta_rd_ptr <= 0;
            update_valid <= 0;
            weight_we <= 0;
            forget_count <= 0;
            prune_count <= 0;
            
        end else if (ce) begin
            case (state)
                IDLE: begin
                    update_valid <= 0;
                    weight_we <= 0;
                    
                    if (pre_valid && pre_ready) begin
                        // 记录前脉冲
                        history_neuron[history_wr_ptr] <= pre_neuron_id;
                        history_time[history_wr_ptr] <= pre_timestamp;
                        history_is_post[history_wr_ptr] <= 0;
                        history_wr_ptr <= history_wr_ptr + 1;
                        history_count <= history_count + 1;
                        state <= RECORD_PRE;
                        
                    end else if (post_valid && post_ready) begin
                        // 记录后脉冲
                        history_neuron[history_wr_ptr] <= post_neuron_id;
                        history_time[history_wr_ptr] <= post_timestamp;
                        history_is_post[history_wr_ptr] <= 1;
                        history_wr_ptr <= history_wr_ptr + 1;
                        history_count <= history_count + 1;
                        state <= RECORD_POST;
                    end
                end
                
                RECORD_PRE: begin
                    search_ptr <= 0;
                    state <= PAIR_SEARCH;
                end
                
                RECORD_POST: begin
                    search_ptr <= 0;
                    state <= PAIR_SEARCH;
                end
                
                PAIR_SEARCH: begin
                    if (search_ptr < history_count) begin
                        if (state == RECORD_PRE) begin
                            // 找后脉冲
                            if (history_is_post[search_ptr]) begin
                                found_pair <= 1;
                                current_post_id <= history_neuron[search_ptr];
                                current_post_time <= history_time[search_ptr];
                                state <= COMPUTE;
                            end else begin
                                search_ptr <= search_ptr + 1;
                            end
                        end else begin
                            // 找前脉冲
                            if (!history_is_post[search_ptr]) begin
                                found_pair <= 1;
                                current_pre_id <= history_neuron[search_ptr];
                                current_pre_time <= history_time[search_ptr];
                                state <= COMPUTE;
                            end else begin
                                search_ptr <= search_ptr + 1;
                            end
                        end
                    end else begin
                        state <= IDLE;
                    end
                end
                
                COMPUTE: begin
                    // 计算时间差
                    if (state == RECORD_PRE) begin
                        dt <= current_post_time - pre_timestamp;
                        current_pre_id <= pre_neuron_id;
                        current_pre_time <= pre_timestamp;
                    end else begin
                        dt <= post_timestamp - current_pre_time;
                        current_post_id <= post_neuron_id;
                        current_post_time <= post_timestamp;
                    end
                    
                    // 计算权重地址
                    weight_addr <= current_pre_id * N_NEURONS + current_post_id;
                    
                    state <= APPLY_FORGET;  // 新增: 先应用遗忘
                end
                
                APPLY_FORGET: begin
                    // 查找上次更新时间
                    reg [9:0] meta_idx;
                    meta_idx = find_weight_meta_index(weight_addr);
                    
                    if (weight_addr_map[meta_idx] == weight_addr) begin
                        // 找到记录，计算遗忘
                        time_since_update <= current_post_time - weight_last_update[meta_idx];
                        
                        // 计算遗忘LUT索引
                        // time_since_update映射到0-255范围
                        if (time_since_update < cfg_tau_forget * 10) begin
                            forget_lut_idx <= (time_since_update * FORGET_LUT_SIZE) / (cfg_tau_forget * 10);
                        end else begin
                            forget_lut_idx <= FORGET_LUT_SIZE - 1;
                        end
                        
                        forget_factor <= forget_lut[forget_lut_idx];
                        
                        // 应用遗忘衰减
                        decayed_weight <= (weight_rdata * forget_factor) >> 8;
                        
                        forget_count <= forget_count + 1;
                    end else begin
                        // 新权重，无遗忘
                        decayed_weight <= weight_rdata;
                    end
                    
                    state <= UPDATE;
                end
                
                UPDATE: begin
                    // 查LUT计算STDP权重变化
                    if (dt > 0 && dt < cfg_max_dt) begin
                        // LTP
                        lut_index <= (dt * 128) / cfg_max_dt;
                        delta_w <= stdp_lut[lut_index];
                    end else if (dt < 0 && -dt < cfg_max_dt) begin
                        // LTD
                        lut_index <= 128 + ((-dt) * 128) / cfg_max_dt;
                        delta_w <= stdp_lut[lut_index];
                    end else begin
                        delta_w <= 0;
                    end
                    
                    // 更新权重 = 遗忘后权重 + STDP变化
                    weight_wdata <= decayed_weight + delta_w;
                    weight_we <= 1;
                    
                    // 更新元数据
                    weight_addr_map[weight_meta_wr_ptr] <= weight_addr;
                    weight_last_update[weight_meta_wr_ptr] <= current_post_time;
                    weight_meta_wr_ptr <= weight_meta_wr_ptr + 1;
                    
                    update_valid <= 1;
                    update_addr <= weight_addr;
                    update_delta <= delta_w;
                    
                    state <= CHECK_PRUNE;
                end
                
                CHECK_PRUNE: begin
                    weight_we <= 0;
                    
                    // 检查是否需要剪枝
                    if ($signed(weight_wdata) < $signed(cfg_forget_thresh) && 
                        $signed(weight_wdata) > -$signed(cfg_forget_thresh)) begin
                        // 权重接近0，标记为可剪枝
                        weight_wdata <= 0;  // 清零
                        prune_count <= prune_count + 1;
                    end
                    
                    state <= OUTPUT;
                end
                
                OUTPUT: begin
                    update_valid <= 0;
                    state <= IDLE;
                end
                
                default: state <= IDLE;
            endcase
            
            // 管理FIFO溢出
            if (history_count >= HISTORY_DEPTH - 8) begin
                history_rd_ptr <= history_rd_ptr + 1;
                history_count <= history_count - 1;
            end
        end
    end

endmodule
