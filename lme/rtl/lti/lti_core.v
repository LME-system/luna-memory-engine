//=============================================================================
// Module: lti_event_encoder
// Description: LTI事件编码器 - 支持T1/T2/T3三层时间坐标
//              将外部事件转换为内部脉冲事件，带时间戳
// Author: Luna Project
// Date: 2026-03-25
//=============================================================================

`timescale 1ns / 1ps

module lti_event_encoder #(
    parameter DATA_WIDTH = 16,
    parameter TIME_WIDTH = 64,          // 支持T3 UTC时间戳 (微秒)
    parameter ADDR_WIDTH = 7,
    parameter VEC_DIM = 512
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    
    // 配置接口
    input  wire [1:0]               cfg_time_mode,      // 00=T1, 01=T2, 10=T3
    input  wire [TIME_WIDTH-1:0]    cfg_t3_offset,      // T3偏移量 (UTC同步)
    
    // 外部事件输入 (AXI-Stream)
    input  wire                     s_axis_valid,
    input  wire [ADDR_WIDTH-1:0]    s_axis_neuron_id,
    input  wire [DATA_WIDTH-1:0]    s_axis_weight,
    input  wire [TIME_WIDTH-1:0]    s_axis_t1,          // 系统时间
    input  wire [31:0]              s_axis_t2_offset,   // 语义时间偏移 (相对)
    output wire                     s_axis_ready,
    
    // 内部脉冲输出 (到LIF核心)
    output reg                      m_axis_valid,
    output reg [ADDR_WIDTH-1:0]     m_axis_neuron_id,
    output reg [DATA_WIDTH-1:0]     m_axis_weight,
    output reg [TIME_WIDTH-1:0]     m_axis_timestamp,   // 统一时间戳
    input  wire                     m_axis_ready,
    
    // T3同步接口 (来自ARM核)
    input  wire                     t3_sync_valid,
    input  wire [TIME_WIDTH-1:0]    t3_sync_value       // NTP同步的UTC时间
);

    //=========================================================================
    // 内部信号
    //=========================================================================
    
    reg [TIME_WIDTH-1:0] t3_reference;      // T3参考时间
    reg [TIME_WIDTH-1:0] t1_last;           // 上次T1时间
    reg t3_synced;                          // T3同步状态
    
    // 时间坐标转换
    reg [TIME_WIDTH-1:0] unified_time;
    reg [TIME_WIDTH-1:0] t2_absolute;       // T2转换为绝对时间
    
    //=========================================================================
    // T3同步逻辑
    //=========================================================================
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            t3_reference <= 0;
            t3_synced <= 0;
        end else begin
            if (t3_sync_valid) begin
                t3_reference <= t3_sync_value;
                t3_synced <= 1;
            end
        end
    end
    
    //=========================================================================
    // 时间坐标转换
    //=========================================================================
    
    always @(*) begin
        case (cfg_time_mode)
            2'b00: begin    // T1: 系统时间 (直接使用)
                unified_time = s_axis_t1;
            end
            
            2'b01: begin    // T2: 语义时间 (相对偏移)
                // T2 = T1 + 语义偏移
                t2_absolute = s_axis_t1 + {{32{s_axis_t2_offset[31]}}, s_axis_t2_offset};
                unified_time = t2_absolute;
            end
            
            2'b10: begin    // T3: 绝对UTC时间
                if (t3_synced) begin
                    // T3 = T1 + (T3参考 - T1参考) = T1 + 偏移
                    unified_time = s_axis_t1 + cfg_t3_offset;
                end else begin
                    // 未同步，回退到T1
                    unified_time = s_axis_t1;
                end
            end
            
            default: unified_time = s_axis_t1;
        endcase
    end
    
    //=========================================================================
    // 事件输出逻辑
    //=========================================================================
    
    assign s_axis_ready = !m_axis_valid || m_axis_ready;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            m_axis_valid <= 0;
            m_axis_neuron_id <= 0;
            m_axis_weight <= 0;
            m_axis_timestamp <= 0;
            t1_last <= 0;
        end else begin
            if (s_axis_valid && s_axis_ready) begin
                m_axis_valid <= 1;
                m_axis_neuron_id <= s_axis_neuron_id;
                m_axis_weight <= s_axis_weight;
                m_axis_timestamp <= unified_time;
                t1_last <= s_axis_t1;
            end else if (m_axis_ready) begin
                m_axis_valid <= 0;
            end
        end
    end

endmodule


//=============================================================================
// Module: lti_vitality_tracker
// Description: 活力追踪器 - 实现记忆活力机制
//              活力 = 访问频率的指数衰减积分
// Author: Luna Project
// Date: 2026-03-25
//=============================================================================

module lti_vitality_tracker #(
    parameter N_NEURONS = 128,
    parameter ADDR_WIDTH = 7,
    parameter VITALITY_WIDTH = 16,      // Q8.8 定点数
    parameter TIME_WIDTH = 64
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     ce,
    
    // 配置接口
    input  wire [VITALITY_WIDTH-1:0] cfg_vitality_tau,      // 活力衰减时间常数
    input  wire [VITALITY_WIDTH-1:0] cfg_vitality_boost,    // 访问增强量
    
    // 访问事件输入
    input  wire                     access_valid,
    input  wire [ADDR_WIDTH-1:0]    access_neuron_id,
    input  wire [TIME_WIDTH-1:0]    access_timestamp,
    
    // 活力查询接口
    input  wire                     query_valid,
    input  wire [ADDR_WIDTH-1:0]    query_neuron_id,
    output reg  [VITALITY_WIDTH-1:0] query_vitality,
    output reg                      query_ready,
    
    // 全局统计
    output reg [ADDR_WIDTH:0]       active_neuron_count,    // 活力>阈值的神经元数
    output reg [VITALITY_WIDTH-1:0] mean_vitality
);

    //=========================================================================
    // 活力状态存储
    //=========================================================================
    
    reg [VITALITY_WIDTH-1:0] vitality [0:N_NEURONS-1];
    reg [TIME_WIDTH-1:0] last_access [0:N_NEURORS-1];
    
    // 泄漏因子: alpha = exp(-dt/tau) ≈ 1 - dt/tau
    wire [VITALITY_WIDTH-1:0] leak_alpha;
    assign leak_alpha = {8'd1, 8'd0} - ({8'd1, 8'd0} / cfg_vitality_tau[15:8]);
    
    //=========================================================================
    // 活力更新逻辑
    //=========================================================================
    
    integer i;
    reg [VITALITY_WIDTH-1:0] v_old, v_new;
    reg [TIME_WIDTH-1:0] time_diff;
    reg [31:0] dt_ms;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < N_NEURONS; i = i + 1) begin
                vitality[i] <= 0;
                last_access[i] <= 0;
            end
            active_neuron_count <= 0;
            mean_vitality <= 0;
            query_ready <= 0;
            
        end else if (ce) begin
            // 处理访问事件: 增强活力
            if (access_valid) begin
                v_old = vitality[access_neuron_id];
                
                // 计算时间差并应用衰减
                time_diff = access_timestamp - last_access[access_neuron_id];
                dt_ms = time_diff[31:0] / 1000;  // 微秒转毫秒
                
                // 衰减: v = v * alpha^dt
                // 简化: 假设dt较小，v ≈ v * (1 - dt/tau)
                v_new = (v_old * leak_alpha) >> 8;
                
                // 增强: 访问即增强
                v_new = v_new + cfg_vitality_boost;
                if (v_new > {8'd2, 8'd0}) v_new = {8'd2, 8'd0};  // 上限2.0
                
                vitality[access_neuron_id] <= v_new;
                last_access[access_neuron_id] <= access_timestamp;
            end
            
            // 处理查询请求
            if (query_valid) begin
                query_vitality <= vitality[query_neuron_id];
                query_ready <= 1;
            end else begin
                query_ready <= 0;
            end
            
            // 周期性统计更新 (每256周期)
            // 实际实现中需要更复杂的统计逻辑
        end
    end

endmodule


//=============================================================================
// Module: lti_top
// Description: LTI顶层模块 - 整合事件编码、活力追踪、Bio-STDP引擎
// Author: Luna Project
// Date: 2026-03-25
//=============================================================================

module lti_top #(
    parameter N_NEURONS = 128,
    parameter DATA_WIDTH = 16,
    parameter TIME_WIDTH = 64,
    parameter ADDR_WIDTH = 7
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    
    // T3同步接口
    input  wire                     t3_sync_valid,
    input  wire [TIME_WIDTH-1:0]    t3_sync_value,
    
    // 配置接口
    input  wire [1:0]               cfg_time_mode,
    
    // 外部事件输入
    input  wire                     s_axis_valid,
    input  wire [ADDR_WIDTH-1:0]    s_axis_neuron_id,
    input  wire [DATA_WIDTH-1:0]    s_axis_weight,
    input  wire [TIME_WIDTH-1:0]    s_axis_t1,
    input  wire [31:0]              s_axis_t2_offset,
    output wire                     s_axis_ready,
    
    // 脉冲输出
    output wire                     m_axis_valid,
    output wire [ADDR_WIDTH-1:0]    m_axis_neuron_id,
    output wire [TIME_WIDTH-1:0]    m_axis_timestamp,
    output wire [DATA_WIDTH-1:0]    m_axis_v_mem,
    input  wire                     m_axis_ready,
    
    // 活力查询
    input  wire                     vitality_query_valid,
    input  wire [ADDR_WIDTH-1:0]    vitality_query_id,
    output wire [15:0]              vitality_query_value,
    output wire                     vitality_query_ready
);

    //=========================================================================
    // 内部信号
    //=========================================================================
    
    wire encoder_valid;
    wire [ADDR_WIDTH-1:0] encoder_neuron_id;
    wire [DATA_WIDTH-1:0] encoder_weight;
    wire [TIME_WIDTH-1:0] encoder_timestamp;
    wire encoder_ready;
    
    //=========================================================================
    // 实例化: 事件编码器
    //=========================================================================
    
    lti_event_encoder #(
        .DATA_WIDTH(DATA_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) u_encoder (
        .clk(clk),
        .rst_n(rst_n),
        .cfg_time_mode(cfg_time_mode),
        .cfg_t3_offset(64'd0),  // 由软件配置
        .s_axis_valid(s_axis_valid),
        .s_axis_neuron_id(s_axis_neuron_id),
        .s_axis_weight(s_axis_weight),
        .s_axis_t1(s_axis_t1),
        .s_axis_t2_offset(s_axis_t2_offset),
        .s_axis_ready(s_axis_ready),
        .m_axis_valid(encoder_valid),
        .m_axis_neuron_id(encoder_neuron_id),
        .m_axis_weight(encoder_weight),
        .m_axis_timestamp(encoder_timestamp),
        .m_axis_ready(encoder_ready),
        .t3_sync_valid(t3_sync_valid),
        .t3_sync_value(t3_sync_value)
    );
    
    //=========================================================================
    // 实例化: 活力追踪器
    //=========================================================================
    
    lti_vitality_tracker #(
        .N_NEURONS(N_NEURONS),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) u_vitality (
        .clk(clk),
        .rst_n(rst_n),
        .ce(1'b1),
        .cfg_vitality_tau(16'h1000),    // tau = 1.0 (约1小时)
        .cfg_vitality_boost(16'h0100),   // boost = 0.0625
        .access_valid(m_axis_valid && m_axis_ready),
        .access_neuron_id(m_axis_neuron_id),
        .access_timestamp(m_axis_timestamp),
        .query_valid(vitality_query_valid),
        .query_neuron_id(vitality_query_id),
        .query_vitality(vitality_query_value),
        .query_ready(vitality_query_ready),
        .active_neuron_count(),
        .mean_vitality()
    );
    
    //=========================================================================
    // 实例化: LIF核心 (来自bio_stdp_engine)
    //=========================================================================
    
    lif_neuron_core #(
        .N_NEURONS(N_NEURONS),
        .DATA_WIDTH(DATA_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) u_lif (
        .clk(clk),
        .rst_n(rst_n),
        .ce(1'b1),
        .cfg_tau_mem(16'h1400),     // 20.0
        .cfg_v_th(16'h0100),        // 1.0
        .cfg_v_reset(16'h0000),     // 0.0
        .cfg_tau_ref(16'd10000),    // 10ms (10000us)
        .s_axis_valid(encoder_valid),
        .s_axis_neuron_id(encoder_neuron_id),
        .s_axis_weight(encoder_weight),
        .s_axis_timestamp(encoder_timestamp),
        .s_axis_ready(encoder_ready),
        .m_axis_valid(m_axis_valid),
        .m_axis_neuron_id(m_axis_neuron_id),
        .m_axis_timestamp(m_axis_timestamp),
        .m_axis_v_mem(m_axis_v_mem),
        .m_axis_ready(m_axis_ready),
        .dbg_v_mem(),
        .dbg_last_spike()
    );

endmodule
