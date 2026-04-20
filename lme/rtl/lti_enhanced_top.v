//=============================================================================
// Module: lti_enhanced_top
// Description: LTI 增强型接口顶层 (~67 IO)
//              32位数据总线 + 高速事件输入 + 实时脉冲输出
//              充分利用 PYNQ-Z2 的 ~75 IO 限制
// Author: Luna Project
// Date: 2026-04-02
//=============================================================================

`timescale 1ns / 1ps

module lti_enhanced_top #(
    parameter N_NEURONS = 128,
    parameter DATA_WIDTH = 16,
    parameter TIME_WIDTH = 64,
    parameter ADDR_WIDTH = 16
)(
    //=========================================================================
    // 系统接口 (2)
    //=========================================================================
    input  wire        clk,
    input  wire        rst_n,
    
    //=========================================================================
    // 地址/命令接口 (16)
    //=========================================================================
    input  wire [15:0] addr,        // 64KB 地址空间
    input  wire        cs_n,        // 片选（低有效）
    input  wire        rw_n,        // 读/写选择（0=写，1=读）
    input  wire        burst,       // 突发传输模式
    
    //=========================================================================
    // 数据接口 (32) - 双向
    //=========================================================================
    inout  wire [31:0] data,        // 32位双向数据总线
    
    //=========================================================================
    // 握手信号 (4)
    //=========================================================================
    input  wire        valid,       // 主机数据有效
    output wire        ready,       // 从机准备好
    output wire        irq_event,   // 可接收事件中断
    output wire        irq_spike,   // 脉冲输出中断
    
    //=========================================================================
    // 高速事件输入接口 (32) - 绕过寄存器，直达核心
    //=========================================================================
    input  wire        event_valid_fast,    // 高速事件有效
    input  wire [6:0]  event_neuron_fast,   // 神经元 ID（0-127）
    input  wire [15:0] event_weight_fast,   // 权重（Q8.8）
    input  wire [7:0]  event_t1_fast,       // 简化时间戳（微秒低8位）
    
    //=========================================================================
    // 实时脉冲输出接口 (16) - 硬件级监控
    //=========================================================================
    output wire        spike_valid_out,     // 脉冲有效
    output wire [6:0]  spike_neuron_out,    // 脉冲神经元 ID
    output wire [7:0]  spike_time_out,      // 脉冲时间戳低8位
    
    //=========================================================================
    // 调试/状态接口 (16)
    //=========================================================================
    output wire [15:0] status_out,          // 实时状态总线
    output wire [3:0]  led,                 // LED 指示
    output wire        heartbeat            // 运行心跳（1Hz）
);

    //=========================================================================
    // 参数定义
    //=========================================================================
    // 地址区域定义
    localparam ADDR_CTRL      = 16'h0000;  // 控制寄存器
    localparam ADDR_STATUS    = 16'h0004;  // 状态寄存器
    localparam ADDR_TIME_MODE = 16'h0008;  // 时间模式
    localparam ADDR_EVENT_BUF = 16'h0100;  // 事件缓冲区起始
    localparam ADDR_SPIKE_BUF = 16'h0200;  // 脉冲缓冲区起始
    localparam ADDR_VITALITY  = 16'h0300;  // 活力查询表
    localparam ADDR_NEURON_CFG= 16'h1000;  // 神经元配置
    localparam ADDR_STDP_WGT  = 16'h2000;  // STDP 权重表
    
    //=========================================================================
    // 内部寄存器
    //=========================================================================
    reg [31:0] reg_ctrl;
    reg [31:0] reg_status;
    reg [1:0]  reg_time_mode;
    reg [15:0] reg_cfg_tau_mem;
    reg [15:0] reg_cfg_v_th;
    
    // 事件组装寄存器
    reg [63:0] event_t1_full;
    reg [6:0]  event_neuron_reg;
    reg [15:0] event_weight_reg;
    reg        event_trigger;
    
    // 双向数据总线控制
    reg [31:0] data_out;
    reg        data_oe;
    
    // 状态机
    localparam IDLE  = 3'b000;
    localparam READ  = 3'b001;
    localparam WRITE = 3'b010;
    localparam BURST = 3'b011;
    reg [2:0] state;
    
    // 握手信号
    reg ready_reg;
    reg irq_event_reg;
    reg irq_spike_reg;
    
    // 心跳计数器
    reg [26:0] heartbeat_cnt;  // 100MHz / 2^27 ≈ 0.75Hz
    reg heartbeat_reg;
    
    //=========================================================================
    // 双向数据总线
    //=========================================================================
    assign data = data_oe ? data_out : 32'bz;
    
    //=========================================================================
    // LTI 核心信号
    //=========================================================================
    wire [TIME_WIDTH-1:0] lti_t1;
    wire [TIME_WIDTH-1:0] lti_t2;
    wire [DATA_WIDTH-1:0] lti_weight;
    wire [6:0]            lti_neuron_id;
    wire                  lti_event_valid;
    wire                  lti_event_ready;
    
    wire [TIME_WIDTH-1:0] lti_spike_time;
    wire [DATA_WIDTH-1:0] lti_spike_v_mem;
    wire [6:0]            lti_spike_neuron;
    wire                  lti_spike_valid;
    
    wire [DATA_WIDTH-1:0] lti_vitality_value;
    
    //=========================================================================
    // 事件源选择：寄存器模式 vs 高速模式
    //=========================================================================
    wire        event_sel_fast = event_valid_fast;
    wire [63:0] event_t1_mux   = event_sel_fast ? 
                                 {56'd0, event_t1_fast} : 
                                 event_t1_full;
    wire [6:0]  event_neuron_mux = event_sel_fast ? 
                                   event_neuron_fast : 
                                   event_neuron_reg;
    wire [15:0] event_weight_mux = event_sel_fast ? 
                                   event_weight_fast : 
                                   event_weight_reg;
    wire        event_valid_mux  = event_sel_fast ? 
                                   event_valid_fast : 
                                   event_trigger;
    
    //=========================================================================
    // 读写控制状态机
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            ready_reg <= 0;
            data_oe <= 0;
            data_out <= 0;
            
            // 寄存器复位
            reg_ctrl <= 0;
            reg_status <= 0;
            reg_time_mode <= 0;
            reg_cfg_tau_mem <= 16'h1400;  // 默认 20.0
            reg_cfg_v_th <= 16'h0100;      // 默认 1.0
            
            event_t1_full <= 0;
            event_neuron_reg <= 0;
            event_weight_reg <= 0;
            event_trigger <= 0;
        end else begin
            // 默认状态
            ready_reg <= 0;
            event_trigger <= 0;
            
            case (state)
                IDLE: begin
                    data_oe <= 0;
                    if (!cs_n && valid) begin
                        if (rw_n) begin
                            // 读操作
                            state <= READ;
                            data_oe <= 1;
                            ready_reg <= 1;
                            
                            case (addr)
                                ADDR_CTRL:       data_out <= reg_ctrl;
                                ADDR_STATUS:     data_out <= reg_status;
                                ADDR_TIME_MODE:  data_out <= {30'd0, reg_time_mode};
                                default:         data_out <= 32'hDEAD_BEEF;
                            endcase
                        end else begin
                            // 写操作
                            state <= burst ? BURST : WRITE;
                            data_oe <= 0;
                            ready_reg <= 1;
                            
                            case (addr)
                                ADDR_CTRL:       reg_ctrl <= data;
                                ADDR_TIME_MODE:  reg_time_mode <= data[1:0];
                                ADDR_EVENT_BUF:  begin
                                    // 事件缓冲区写入
                                    event_t1_full <= {event_t1_full[31:0], data};
                                end
                                ADDR_EVENT_BUF+4: begin
                                    event_neuron_reg <= data[6:0];
                                    event_weight_reg <= data[31:16];
                                    event_trigger <= 1;  // 触发
                                end
                                default: ;
                            endcase
                        end
                    end
                end
                
                READ: begin
                    if (cs_n) begin
                        state <= IDLE;
                        data_oe <= 0;
                    end
                end
                
                WRITE: begin
                    if (cs_n) begin
                        state <= IDLE;
                    end
                end
                
                BURST: begin
                    // 突发传输模式
                    if (cs_n) begin
                        state <= IDLE;
                    end else if (valid) begin
                        ready_reg <= 1;
                        // 连续写入事件缓冲区
                    end
                end
            endcase
        end
    end
    
    //=========================================================================
    // 状态更新
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_status <= 0;
        end else begin
            reg_status[0] <= lti_event_ready;
            reg_status[1] <= lti_spike_valid;
            reg_status[7:2] <= 0;
            reg_status[15:8] <= event_neuron_reg;  // 最后事件神经元
        end
    end
    
    //=========================================================================
    // 心跳生成 (~1Hz @ 100MHz)
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            heartbeat_cnt <= 0;
            heartbeat_reg <= 0;
        end else begin
            if (heartbeat_cnt == 27'd99_999_999) begin
                heartbeat_cnt <= 0;
                heartbeat_reg <= ~heartbeat_reg;
            end else begin
                heartbeat_cnt <= heartbeat_cnt + 1;
            end
        end
    end
    
    //=========================================================================
    // LTI 核心实例化
    //=========================================================================
    assign lti_t1 = event_t1_mux;
    assign lti_t2 = 0;  // 简化，T2 由软件计算
    assign lti_weight = event_weight_mux;
    assign lti_neuron_id = event_neuron_mux;
    assign lti_event_valid = event_valid_mux;
    
    lti_top lti_core (
        .clk(clk),
        .rst_n(rst_n && !reg_ctrl[0]),
        .t3_sync_valid(1'b0),
        .t3_sync_value(64'd0),
        .cfg_time_mode(reg_time_mode),
        .s_axis_valid(lti_event_valid),
        .s_axis_neuron_id(lti_neuron_id),
        .s_axis_weight(lti_weight),
        .s_axis_t1(lti_t1),
        .s_axis_t2_offset(32'd0),
        .s_axis_ready(lti_event_ready),
        .m_axis_valid(lti_spike_valid),
        .m_axis_neuron_id(lti_spike_neuron),
        .m_axis_timestamp(lti_spike_time),
        .m_axis_v_mem(lti_spike_v_mem),
        .m_axis_ready(1'b1),
        .vitality_query_valid(1'b0),
        .vitality_query_id(7'd0),
        .vitality_query_value(lti_vitality_value),
        .vitality_query_ready()
    );
    
    //=========================================================================
    // 输出赋值
    //=========================================================================
    assign ready = ready_reg;
    assign irq_event = lti_event_ready;
    assign irq_spike = lti_spike_valid;
    
    // 实时脉冲输出
    assign spike_valid_out = lti_spike_valid;
    assign spike_neuron_out = lti_spike_neuron;
    assign spike_time_out = lti_spike_time[7:0];
    
    // 状态输出
    assign status_out = {
        lti_spike_valid,      // [15]
        lti_event_ready,      // [14]
        6'd0,                 // [13:8]
        event_neuron_reg      // [7:0]
    };
    
    // LED 指示
    assign led = {
        lti_spike_valid,      // LED3: 脉冲指示
        lti_event_ready,      // LED2: 就绪指示
        state[1:0]            // LED1-0: 状态指示
    };
    
    assign heartbeat = heartbeat_reg;

endmodule
