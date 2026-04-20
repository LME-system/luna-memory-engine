//=============================================================================
// Module: lme_export_bridge
// Description: LME数据导出接口 - Phase 1实现
//              将FPGA内部状态导出到Python/月痕系统
// Author: Luna Project
// Date: 2026-04-14
//=============================================================================

`timescale 1ns / 1ps

module lme_export_bridge #(
    parameter N_NEURONS = 128,
    parameter DATA_WIDTH = 16,
    parameter TIME_WIDTH = 64,
    parameter ADDR_WIDTH = 7,
    parameter EXPORT_BATCH_SIZE = 16  // 每批导出16个神经元
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    
    // 控制接口 (来自ARM/CPU)
    input  wire                     export_start,       // 开始导出
    input  wire [1:0]               export_mode,        // 00=活力, 01=权重, 10=因果图, 11=全量
    input  wire [ADDR_WIDTH-1:0]    export_start_addr,  // 起始神经元地址
    output reg                      export_done,        // 导出完成
    output reg                      export_busy,        // 导出进行中
    
    // 状态输入 (来自LME核心)
    input  wire [DATA_WIDTH-1:0]    vitality_in [0:N_NEURONS-1],      // 活力值
    input  wire [DATA_WIDTH-1:0]    weights_in [0:N_NEURONS-1][0:N_NEURONS-1], // 权重矩阵
    input  wire [TIME_WIDTH-1:0]    last_spike_time [0:N_NEURONS-1],  // 上次脉冲时间
    input  wire [N_NEURONS-1:0]     active_mask,                      // 活跃掩码
    
    // AXI-Lite接口 (导出数据到CPU)
    // 读地址通道
    input  wire [ADDR_WIDTH+3:0]    s_axi_araddr,       // 地址 + 偏移
    input  wire                     s_axi_arvalid,
    output reg                      s_axi_arready,
    
    // 读数据通道
    output reg [31:0]               s_axi_rdata,
    output reg [1:0]                s_axi_rresp,
    output reg                      s_axi_rvalid,
    input  wire                     s_axi_rready,
    
    // 中断输出
    output reg                      irq_export_ready    // 导出完成中断
);

    //=========================================================================
    // 状态机定义
    //=========================================================================
    
    localparam STATE_IDLE = 3'd0;
    localparam STATE_EXPORT_VITALITY = 3'd1;
    localparam STATE_EXPORT_WEIGHTS = 3'd2;
    localparam STATE_EXPORT_CAUSAL = 3'd3;
    localparam STATE_EXPORT_FULL = 3'd4;
    localparam STATE_DONE = 3'd5;
    
    reg [2:0] state, next_state;
    
    //=========================================================================
    // 导出缓冲区
    //=========================================================================
    
    // 双缓冲设计：FPGA填充Buffer A，CPU读取Buffer B
    reg [DATA_WIDTH-1:0] export_buffer_a [0:EXPORT_BATCH_SIZE-1];
    reg [DATA_WIDTH-1:0] export_buffer_b [0:EXPORT_BATCH_SIZE-1];
    reg buffer_a_ready, buffer_b_ready;
    reg buffer_select;  // 0=A是写入缓冲, 1=B是写入缓冲
    
    // 导出计数器
    reg [ADDR_WIDTH:0] export_counter;  // 0 to N_NEURONS
    reg [ADDR_WIDTH:0] batch_counter;   // 0 to EXPORT_BATCH_SIZE
    
    //=========================================================================
    // 状态机 - 时序逻辑
    //=========================================================================
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= STATE_IDLE;
            export_counter <= 0;
            batch_counter <= 0;
            buffer_select <= 0;
            buffer_a_ready <= 0;
            buffer_b_ready <= 0;
            export_done <= 0;
            export_busy <= 0;
            irq_export_ready <= 0;
        end else begin
            state <= next_state;
            
            case (state)
                STATE_IDLE: begin
                    export_done <= 0;
                    irq_export_ready <= 0;
                    if (export_start) begin
                        export_busy <= 1;
                        export_counter <= export_start_addr;
                        batch_counter <= 0;
                    end
                end
                
                STATE_EXPORT_VITALITY: begin
                    // 填充当前批次
                    if (batch_counter < EXPORT_BATCH_SIZE && export_counter < N_NEURONS) begin
                        if (buffer_select == 0) begin
                            export_buffer_a[batch_counter] <= vitality_in[export_counter];
                        end else begin
                            export_buffer_b[batch_counter] <= vitality_in[export_counter];
                        end
                        export_counter <= export_counter + 1;
                        batch_counter <= batch_counter + 1;
                    end else begin
                        // 批次完成，切换缓冲
                        if (buffer_select == 0) begin
                            buffer_a_ready <= 1;
                        end else begin
                            buffer_b_ready <= 1;
                        end
                        buffer_select <= ~buffer_select;
                        batch_counter <= 0;
                        
                        // 检查是否全部完成
                        if (export_counter >= N_NEURONS) begin
                            export_done <= 1;
                            irq_export_ready <= 1;
                        end
                    end
                end
                
                STATE_EXPORT_WEIGHTS: begin
                    // TODO: 权重矩阵导出（稀疏格式）
                end
                
                STATE_EXPORT_CAUSAL: begin
                    // TODO: 因果图导出（边列表）
                end
                
                STATE_EXPORT_FULL: begin
                    // TODO: 全量导出
                end
                
                STATE_DONE: begin
                    export_busy <= 0;
                    buffer_a_ready <= 0;
                    buffer_b_ready <= 0;
                end
            endcase
        end
    end
    
    //=========================================================================
    // 状态机 - 组合逻辑
    //=========================================================================
    
    always @(*) begin
        next_state = state;
        
        case (state)
            STATE_IDLE: begin
                if (export_start) begin
                    case (export_mode)
                        2'b00: next_state = STATE_EXPORT_VITALITY;
                        2'b01: next_state = STATE_EXPORT_WEIGHTS;
                        2'b10: next_state = STATE_EXPORT_CAUSAL;
                        2'b11: next_state = STATE_EXPORT_FULL;
                        default: next_state = STATE_EXPORT_VITALITY;
                    endcase
                end
            end
            
            STATE_EXPORT_VITALITY: begin
                if (export_done) begin
                    next_state = STATE_DONE;
                end
            end
            
            STATE_EXPORT_WEIGHTS: begin
                next_state = STATE_DONE;  // 简化
            end
            
            STATE_EXPORT_CAUSAL: begin
                next_state = STATE_DONE;  // 简化
            end
            
            STATE_EXPORT_FULL: begin
                next_state = STATE_DONE;  // 简化
            end
            
            STATE_DONE: begin
                next_state = STATE_IDLE;
            end
        endcase
    end
    
    //=========================================================================
    // AXI-Lite读接口
    //=========================================================================
    
    // 地址解码
    wire [ADDR_WIDTH+1:0] word_addr = s_axi_araddr[ADDR_WIDTH+3:2];  // 字地址
    wire [3:0] reg_offset = s_axi_araddr[5:2];  // 寄存器内偏移
    
    // 寄存器映射
    // 0x00: 控制/状态
    // 0x01: 导出模式
    // 0x02: 当前批次大小
    // 0x03-0x12: 数据缓冲区 (16个word)
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_axi_arready <= 0;
            s_axi_rvalid <= 0;
            s_axi_rdata <= 0;
            s_axi_rresp <= 0;
        end else begin
            // 默认
            s_axi_arready <= 0;
            
            if (s_axi_arvalid && !s_axi_rvalid) begin
                s_axi_arready <= 1;
                s_axi_rvalid <= 1;
                s_axi_rresp <= 2'b00;  // OKAY
                
                case (reg_offset)
                    4'd0: begin  // 状态寄存器
                        s_axi_rdata <= {28'd0, export_busy, export_done, buffer_b_ready, buffer_a_ready};
                    end
                    
                    4'd1: begin  // 模式/计数
                        s_axi_rdata <= {16'd0, export_counter, 2'd0, export_mode};
                    end
                    
                    4'd2: begin  // 批次大小
                        s_axi_rdata <= EXPORT_BATCH_SIZE;
                    end
                    
                    4'd3, 4'd4, 4'd5, 4'd6, 4'd7, 4'd8, 4'd9, 4'd10,
                    4'd11, 4'd12, 4'd13, 4'd14, 4'd15, 4'd16, 4'd17, 4'd18: begin
                        // 数据缓冲区
                        if (buffer_select == 0) begin
                            // 当前B是读取缓冲
                            s_axi_rdata <= {{(32-DATA_WIDTH){1'b0}}, export_buffer_b[reg_offset-3]};
                        end else begin
                            // 当前A是读取缓冲
                            s_axi_rdata <= {{(32-DATA_WIDTH){1'b0}}, export_buffer_a[reg_offset-3]};
                        end
                    end
                    
                    default: begin
                        s_axi_rdata <= 32'hDEADBEEF;
                    end
                endcase
            end else if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 0;
            end
        end
    end
    
    //=========================================================================
    // 调试/监控
    //=========================================================================
    
    // 导出统计
    reg [31:0] export_cycle_count;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            export_cycle_count <= 0;
        end else begin
            if (export_busy) begin
                export_cycle_count <= export_cycle_count + 1;
            end else begin
                export_cycle_count <= 0;
            end
        end
    end

endmodule


//=============================================================================
// Module: lme_yuehen_fusion_top
// Description: LME-月痕融合顶层模块
//              整合LME核心 + 数据导出桥 + 同步控制
//=============================================================================

module lme_yuehen_fusion_top #(
    parameter N_NEURONS = 128,
    parameter DATA_WIDTH = 16,
    parameter TIME_WIDTH = 64,
    parameter ADDR_WIDTH = 7
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    
    // AXI-Lite配置接口
    input  wire [ADDR_WIDTH+3:0]    s_axi_awaddr,
    input  wire                     s_axi_awvalid,
    output wire                     s_axi_awready,
    input  wire [31:0]              s_axi_wdata,
    input  wire [3:0]               s_axi_wstrb,
    input  wire                     s_axi_wvalid,
    output wire                     s_axi_wready,
    output wire [1:0]               s_axi_bresp,
    output wire                     s_axi_bvalid,
    input  wire                     s_axi_bready,
    
    input  wire [ADDR_WIDTH+3:0]    s_axi_araddr,
    input  wire                     s_axi_arvalid,
    output wire                     s_axi_arready,
    output wire [31:0]              s_axi_rdata,
    output wire [1:0]               s_axi_rresp,
    output wire                     s_axi_rvalid,
    input  wire                     s_axi_rready,
    
    // 事件输入接口
    input  wire                     event_valid,
    input  wire [ADDR_WIDTH-1:0]    event_neuron_id,
    input  wire [DATA_WIDTH-1:0]    event_weight,
    output wire                     event_ready,
    
    // 中断输出
    output wire                     irq_spike,
    output wire                     irq_export_ready,
    
    // 调试接口
    output wire [7:0]               debug_state
);

    //=========================================================================
    // 内部信号
    //=========================================================================
    
    // LME核心信号
    wire [DATA_WIDTH-1:0] vitality [0:N_NEURONS-1];
    wire [N_NEURONS-1:0] active_mask;
    
    // 导出控制
    reg export_start;
    reg [1:0] export_mode;
    wire export_done;
    wire export_busy;
    
    //=========================================================================
    // 配置寄存器
    //=========================================================================
    
    reg [31:0] ctrl_reg;        // 0x00: 控制寄存器
    reg [31:0] mode_reg;        // 0x04: 模式寄存器
    reg [31:0] status_reg;      // 0x08: 状态寄存器 (只读)
    
    // 控制位定义
    wire ctrl_export_start = ctrl_reg[0];
    wire ctrl_reset_lme = ctrl_reg[1];
    
    //=========================================================================
    // AXI-Lite写逻辑
    //=========================================================================
    
    reg awready_reg, wready_reg, bvalid_reg;
    reg [1:0] bresp_reg;
    
    assign s_axi_awready = awready_reg;
    assign s_axi_wready = wready_reg;
    assign s_axi_bvalid = bvalid_reg;
    assign s_axi_bresp = bresp_reg;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            awready_reg <= 0;
            wready_reg <= 0;
            bvalid_reg <= 0;
            bresp_reg <= 0;
            ctrl_reg <= 0;
            mode_reg <= 0;
        end else begin
            // 地址握手
            if (s_axi_awvalid && !awready_reg) begin
                awready_reg <= 1;
            end else begin
                awready_reg <= 0;
            end
            
            // 数据握手
            if (s_axi_wvalid && !wready_reg) begin
                wready_reg <= 1;
                
                // 写寄存器
                case (s_axi_awaddr[5:2])
                    4'd0: ctrl_reg <= s_axi_wdata;
                    4'd1: mode_reg <= s_axi_wdata;
                endcase
            end else begin
                wready_reg <= 0;
            end
            
            // 响应
            if (awready_reg && wready_reg) begin
                bvalid_reg <= 1;
                bresp_reg <= 2'b00;
            end else if (s_axi_bready && bvalid_reg) begin
                bvalid_reg <= 0;
            end
            
            // 自动清除start位
            if (ctrl_reg[0]) begin
                ctrl_reg[0] <= 0;
            end
        end
    end
    
    //=========================================================================
    // 导出桥实例化
    //=========================================================================
    
    lme_export_bridge #(
        .N_NEURONS(N_NEURONS),
        .DATA_WIDTH(DATA_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH),
        .EXPORT_BATCH_SIZE(16)
    ) u_export_bridge (
        .clk(clk),
        .rst_n(rst_n),
        .export_start(ctrl_export_start),
        .export_mode(mode_reg[1:0]),
        .export_start_addr(0),
        .export_done(export_done),
        .export_busy(export_busy),
        .vitality_in(vitality),
        .weights_in('{default: 0}),  // 简化
        .last_spike_time('{default: 0}),
        .active_mask(active_mask),
        .s_axi_araddr(s_axi_araddr),
        .s_axi_arvalid(s_axi_arvalid),
        .s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),
        .s_axi_rresp(s_axi_rresp),
        .s_axi_rvalid(s_axi_rvalid),
        .s_axi_rready(s_axi_rready),
        .irq_export_ready(irq_export_ready)
    );
    
    //=========================================================================
    // LME核心实例化 (简化版)
    //=========================================================================
    
    // 活力生成逻辑 (简化)
    genvar i;
    generate
        for (i = 0; i < N_NEURORS; i = i + 1) begin : gen_vitality
            assign vitality[i] = event_valid && (event_neuron_id == i) ? 
                                 event_weight : 16'h1000;  // 默认活力
            assign active_mask[i] = (vitality[i] > 16'h0800);
        end
    endgenerate
    
    //=========================================================================
    // 输出赋值
    //=========================================================================
    
    assign event_ready = 1'b1;  // 总是就绪
    assign irq_spike = event_valid;
    assign debug_state = {export_busy, export_done, 6'b0};

endmodule
