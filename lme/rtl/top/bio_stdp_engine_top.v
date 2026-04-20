//=============================================================================
// Module: bio_stdp_engine_top
// Description: Bio-STDP Engine顶层模块，整合所有核心组件
// Author: Luna Project
// Date: 2026-03-24
//=============================================================================

`timescale 1ns / 1ps

module bio_stdp_engine_top #(
    parameter N_NEURONS = 128,
    parameter DATA_WIDTH = 16,
    parameter TIME_WIDTH = 32,
    parameter ADDR_WIDTH = 7
)(
    // 系统接口
    input  wire                     aclk,
    input  wire                     aresetn,
    
    // AXI-Lite配置接口
    input  wire [31:0]              s_axi_awaddr,
    input  wire                     s_axi_awvalid,
    output wire                     s_axi_awready,
    input  wire [31:0]              s_axi_wdata,
    input  wire [3:0]               s_axi_wstrb,
    input  wire                     s_axi_wvalid,
    output wire                     s_axi_wready,
    output wire [1:0]               s_axi_bresp,
    output wire                     s_axi_bvalid,
    input  wire                     s_axi_bready,
    input  wire [31:0]              s_axi_araddr,
    input  wire                     s_axi_arvalid,
    output wire                     s_axi_arready,
    output wire [31:0]              s_axi_rdata,
    output wire [1:0]               s_axi_rresp,
    output wire                     s_axi_rvalid,
    input  wire                     s_axi_rready,
    
    // AXI-Stream输入 (事件)
    input  wire                     s_axis_tvalid,
    input  wire [31:0]              s_axis_tdata,   // {neuron_id[7:0], weight[15:0], reserved[7:0]}
    input  wire                     s_axis_tlast,
    output wire                     s_axis_tready,
    
    // AXI-Stream输出 (因果向量)
    output wire                     m_axis_tvalid,
    output wire [31:0]              m_axis_tdata,
    output wire                     m_axis_tlast,
    input  wire                     m_axis_tready,
    
    // 调试接口
    output wire [15:0]              dbg_status,
    output wire [31:0]              dbg_event_count
);

    //=========================================================================
    // 寄存器映射
    //=========================================================================
    
    // 0x00: 控制寄存器
    //   [0]: ap_start
    //   [1]: ap_done (RO)
    //   [2]: ap_idle (RO)
    // 0x04: 全局配置
    //   [15:0]:  tau_mem
    // 0x08: LIF配置
    //   [15:0]:  v_th
    //   [31:16]: v_reset
    // 0x0C: STDP配置
    //   [15:0]:  A_plus
    //   [31:16]: A_minus
    // 0x10: 状态 (RO)
    //   [15:0]:  fifo_fill_level
    // 0x14: 事件计数 (RO)
    
    //=========================================================================
    // 寄存器定义
    //=========================================================================
    
    reg ap_start, ap_done, ap_idle;
    reg [DATA_WIDTH-1:0] reg_tau_mem;
    reg [DATA_WIDTH-1:0] reg_v_th;
    reg [DATA_WIDTH-1:0] reg_v_reset;
    reg [DATA_WIDTH-1:0] reg_A_plus;
    reg [DATA_WIDTH-1:0] reg_A_minus;
    reg [15:0] reg_tau_ref;
    reg [31:0] event_counter;
    
    // AXI-Lite状态机
    reg [2:0] axi_state;
    localparam AXI_IDLE = 3'b000;
    localparam AXI_WRITE = 3'b001;
    localparam AXI_WRITE_RESP = 3'b010;
    localparam AXI_READ = 3'b011;
    localparam AXI_READ_RESP = 3'b100;
    
    reg [31:0] axi_awaddr;
    reg [31:0] axi_araddr;
    
    // AXI-Lite握手信号
    assign s_axi_awready = (axi_state == AXI_IDLE);
    assign s_axi_wready = (axi_state == AXI_WRITE);
    assign s_axi_bresp = 2'b00;
    assign s_axi_bvalid = (axi_state == AXI_WRITE_RESP);
    assign s_axi_arready = (axi_state == AXI_IDLE);
    assign s_axi_rresp = 2'b00;
    assign s_axi_rvalid = (axi_state == AXI_READ_RESP);
    
    // 读数据
    assign s_axi_rdata = (axi_araddr == 32'h00) ? {29'b0, ap_idle, ap_done, ap_start} :
                         (axi_araddr == 32'h04) ? {16'b0, reg_tau_mem} :
                         (axi_araddr == 32'h08) ? {reg_v_reset, reg_v_th} :
                         (axi_araddr == 32'h0C) ? {reg_A_minus, reg_A_plus} :
                         (axi_araddr == 32'h10) ? {16'b0, fifo_fill_level} :
                         (axi_araddr == 32'h14) ? event_counter :
                         32'hDEADBEEF;
    
    // AXI-Lite状态机
    always @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            axi_state <= AXI_IDLE;
            ap_start <= 0;
            reg_tau_mem <= 16'h1400;  // 20.0
            reg_v_th <= 16'h0100;     // 1.0
            reg_v_reset <= 16'h0000;  // 0.0
            reg_A_plus <= 16'h0003;   // 0.01
            reg_A_minus <= 16'hFFFD;  // -0.01
            reg_tau_ref <= 16'h2710;  // 10000us = 10ms
        end else begin
            case (axi_state)
                AXI_IDLE: begin
                    ap_start <= 0;
                    if (s_axi_awvalid) begin
                        axi_awaddr <= s_axi_awaddr;
                        axi_state <= AXI_WRITE;
                    end else if (s_axi_arvalid) begin
                        axi_araddr <= s_axi_araddr;
                        axi_state <= AXI_READ;
                    end
                end
                
                AXI_WRITE: begin
                    if (s_axi_wvalid) begin
                        // 写寄存器
                        case (axi_awaddr)
                            32'h00: ap_start <= s_axi_wdata[0];
                            32'h04: reg_tau_mem <= s_axi_wdata[15:0];
                            32'h08: begin
                                reg_v_th <= s_axi_wdata[15:0];
                                reg_v_reset <= s_axi_wdata[31:16];
                            end
                            32'h0C: begin
                                reg_A_plus <= s_axi_wdata[15:0];
                                reg_A_minus <= s_axi_wdata[31:16];
                            end
                            32'h18: reg_tau_ref <= s_axi_wdata[15:0];
                        endcase
                        axi_state <= AXI_WRITE_RESP;
                    end
                end
                
                AXI_WRITE_RESP: begin
                    if (s_axi_bready) begin
                        axi_state <= AXI_IDLE;
                    end
                end
                
                AXI_READ: begin
                    axi_state <= AXI_READ_RESP;
                end
                
                AXI_READ_RESP: begin
                    if (s_axi_rready) begin
                        axi_state <= AXI_IDLE;
                    end
                end
                
                default: axi_state <= AXI_IDLE;
            endcase
        end
    end
    
    //=========================================================================
    // 内部信号连接
    //=========================================================================
    
    wire [ADDR_WIDTH-1:0] lif_neuron_id;
    wire [DATA_WIDTH-1:0] lif_weight;
    wire [TIME_WIDTH-1:0] lif_timestamp;
    wire lif_valid;
    wire lif_ready;
    
    wire [ADDR_WIDTH-1:0] lif_spike_id;
    wire [TIME_WIDTH-1:0] lif_spike_time;
    wire [DATA_WIDTH-1:0] lif_spike_vmem;
    wire lif_spike_valid;
    wire lif_spike_ready;
    
    wire [1:0] route_table [0:N_NEURONS-1];
    
    // 路由表: 0=LIF, 1=STDP, 2=DG, 3=CA3
    assign route_table[0] = 2'b00;  // 默认路由到LIF
    
    // FIFO填充状态
    wire [23:0] fifo_fill_level;
    
    //=========================================================================
    // 事件输入解析
    //=========================================================================
    
    reg [ADDR_WIDTH-1:0] parsed_neuron_id;
    reg [DATA_WIDTH-1:0] parsed_weight;
    reg [TIME_WIDTH-1:0] parsed_timestamp;
    reg parsed_valid;
    
    assign s_axis_tready = ap_idle;
    
    always @(posedge aclk) begin
        if (ap_start) begin
            ap_idle <= 0;
        end
        
        if (s_axis_tvalid && s_axis_tready) begin
            parsed_neuron_id <= s_axis_tdata[6:0];
            parsed_weight <= s_axis_tdata[23:8];
            parsed_timestamp <= $time;  // 使用仿真时间或外部计数器
            parsed_valid <= 1;
            event_counter <= event_counter + 1;
        end else begin
            parsed_valid <= 0;
        end
        
        if (s_axis_tlast) begin
            ap_done <= 1;
            ap_idle <= 1;
        end
    end
    
    //=========================================================================
    // 实例化: 事件路由器
    //=========================================================================
    
    event_router #(
        .N_INPUTS(1),
        .N_OUTPUTS(4),
        .FIFO_DEPTH(32),
        .TIME_WIDTH(TIME_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) u_event_router (
        .clk(aclk),
        .rst_n(aresetn),
        .ce(1'b1),
        .route_table(route_table),
        
        .in_valid(parsed_valid),
        .in_neuron_id(parsed_neuron_id),
        .in_weight(parsed_weight),
        .in_timestamp(parsed_timestamp),
        .in_ready(),
        
        .out_valid({ca3_valid, dg_valid, stdp_valid, lif_valid}),
        .out_neuron_id({ca3_neuron_id, dg_neuron_id, stdp_neuron_id, lif_neuron_id}),
        .out_weight({ca3_weight, dg_weight, stdp_weight, lif_weight}),
        .out_timestamp({ca3_time, dg_time, stdp_time, lif_timestamp}),
        .out_ready({ca3_ready, dg_ready, stdp_ready, lif_ready}),
        
        .fifo_fill_level(fifo_fill_level)
    );
    
    //=========================================================================
    // 实例化: LIF神经元阵列
    //=========================================================================
    
    lif_neuron_core #(
        .N_NEURONS(N_NEURONS),
        .DATA_WIDTH(DATA_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) u_lif_core (
        .clk(aclk),
        .rst_n(aresetn),
        .ce(1'b1),
        
        .cfg_tau_mem(reg_tau_mem),
        .cfg_v_th(reg_v_th),
        .cfg_v_reset(reg_v_reset),
        .cfg_tau_ref(reg_tau_ref),
        
        .s_axis_valid(lif_valid),
        .s_axis_neuron_id(lif_neuron_id),
        .s_axis_weight(lif_weight),
        .s_axis_timestamp(lif_timestamp),
        .s_axis_ready(lif_ready),
        
        .m_axis_valid(lif_spike_valid),
        .m_axis_neuron_id(lif_spike_id),
        .m_axis_timestamp(lif_spike_time),
        .m_axis_v_mem(lif_spike_vmem),
        .m_axis_ready(lif_spike_ready),
        
        .dbg_v_mem(),
        .dbg_last_spike()
    );
    
    //=========================================================================
    // 输出聚合 (简化: 直接输出LIF脉冲)
    //=========================================================================
    
    assign m_axis_tvalid = lif_spike_valid;
    assign m_axis_tdata = {8'b0, lif_spike_vmem, lif_spike_id};
    assign m_axis_tlast = 1'b0;
    assign lif_spike_ready = m_axis_tready;
    
    //=========================================================================
    // 调试输出
    //=========================================================================
    
    assign dbg_status = {8'b0, fifo_fill_level[7:0]};
    assign dbg_event_count = event_counter;

endmodule
