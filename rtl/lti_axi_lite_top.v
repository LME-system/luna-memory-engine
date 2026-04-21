//=============================================================================
// Module: lti_axi_lite_top
// Description: LTI (Luna Temporal Index) AXI-Lite 封装顶层
//              为 PYNQ-Z2 优化的精简接口版本
// Author: Luna Project
// Date: 2026-04-05
//=============================================================================

`timescale 1ns / 1ps

module lti_axi_lite_top #(
    parameter N_NEURONS = 128,
    parameter DATA_WIDTH = 16,
    parameter TIME_WIDTH = 64,
    parameter ADDR_WIDTH = 7
)(
    //=========================================================================
    // 系统接口
    //=========================================================================
    input  wire        clk,
    input  wire        rst_n,
    
    //=========================================================================
    // AXI-Lite 从接口
    //=========================================================================
    // 写地址通道
    input  wire [11:0] s_axi_awaddr,   // 4KB 地址空间
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    
    // 写数据通道
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    
    // 写响应通道
    output wire [1:0]  s_axi_bresp,
    output wire        s_axi_bvalid,
    input  wire        s_axi_bready,
    
    // 读地址通道
    input  wire [11:0] s_axi_araddr,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    
    // 读数据通道
    output wire [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output wire        s_axi_rvalid,
    input  wire        s_axi_rready,
    
    //=========================================================================
    // 中断输出
    //=========================================================================
    output wire        irq_event_ready,  // 可接收新事件
    output wire        irq_spike_valid   // 有脉冲输出
);

    //=========================================================================
    // 寄存器地址定义
    //=========================================================================
    localparam REG_CTRL = 12'h000;        // 控制寄存器
    localparam REG_STATUS = 12'h004;      // 状态寄存器
    localparam REG_TIME_MODE = 12'h008;   // 时间模式
    localparam REG_EVENT_T1_HI = 12'h020; // 事件 T1[63:32]
    localparam REG_EVENT_T1_LO = 12'h024; // 事件 T1[31:0]
    localparam REG_EVENT_T2 = 12'h028;    // 事件 T2
    localparam REG_EVENT_NEURON = 12'h02C;// 事件神经元 ID
    localparam REG_EVENT_WEIGHT = 12'h030;// 事件权重
    localparam REG_EVENT_TRIGGER = 12'h034;// 事件触发
    localparam REG_VITALITY_ID = 12'h040; // 查询神经元 ID
    localparam REG_VITALITY_VALUE = 12'h044;// 活力值（只读）
    localparam REG_SPIKE_VALID = 12'h050; // 脉冲有效（只读）
    localparam REG_SPIKE_NEURON = 12'h054;// 脉冲神经元 ID（只读）
    localparam REG_SPIKE_TIME_HI = 12'h058;// 脉冲时间[63:32]（只读）
    localparam REG_SPIKE_TIME_LO = 12'h05C;// 脉冲时间[31:0]（只读）
    localparam REG_SPIKE_V_MEM = 12'h060; // 脉冲膜电位（只读）
    localparam REG_VERSION = 12'h0FC;     // 版本号（只读）
    
    //=========================================================================
    // 数据导出接口地址空间 (0x400-0x7FF)
    //=========================================================================
    localparam EXPORT_BASE_ADDR = 12'h400;
    localparam EXPORT_ADDR_MASK = 12'h3FF;  // 1KB 地址空间
    
    // 导出寄存器偏移
    localparam EXPORT_CTRL        = 8'h00;  // 导出控制
    localparam EXPORT_STATUS      = 8'h04;  // 导出状态
    localparam EXPORT_NEURON_ID   = 8'h08;  // 当前导出神经元ID
    localparam EXPORT_VITALITY    = 8'h0C;  // 活力值
    localparam EXPORT_V_MEM       = 8'h10;  // 膜电位
    localparam EXPORT_LAST_SPIKE  = 8'h14;  // 上次发放时间
    localparam EXPORT_WEIGHT_BASE = 8'h20;  // 权重矩阵起始 (0x420)

    //=========================================================================
    // 内部寄存器
    //=========================================================================
    reg [31:0] reg_ctrl;
    reg [31:0] reg_status;
    reg [1:0]  reg_time_mode;
    
    // 事件寄存器
    reg [63:0] reg_event_t1;
    reg [31:0] reg_event_t2;
    reg [6:0]  reg_event_neuron;
    reg [15:0] reg_event_weight;
    
    // 查询寄存器
    reg [6:0]  reg_vitality_id;
    
    //=========================================================================
    // 数据导出接口寄存器
    //=========================================================================
    reg [31:0] export_ctrl_reg;
    reg [6:0]  export_neuron_id_reg;
    reg        export_active;
    reg [31:0] export_status_reg;
    
    // 导出状态定义
    localparam EXPORT_IDLE  = 2'b00;
    localparam EXPORT_BUSY  = 2'b01;
    localparam EXPORT_DONE  = 2'b10;
    reg [1:0]  export_state;
    
    // AXI-Lite 握手信号
    reg        awready_reg;
    reg        wready_reg;
    reg [1:0]  bresp_reg;
    reg        bvalid_reg;
    reg        arready_reg;
    reg [31:0] rdata_reg;
    reg [1:0]  rresp_reg;
    reg        rvalid_reg;

    //=========================================================================
    // LTI 核心实例化信号
    //=========================================================================
    wire [TIME_WIDTH-1:0] lti_t1;
    wire [31:0]           lti_t2_offset;
    wire [DATA_WIDTH-1:0] lti_weight;
    wire [ADDR_WIDTH-1:0] lti_neuron_id;
    wire                  lti_event_valid;
    wire                  lti_event_ready;
    
    wire [TIME_WIDTH-1:0] lti_spike_time;
    wire [DATA_WIDTH-1:0] lti_spike_v_mem;
    wire [ADDR_WIDTH-1:0] lti_spike_neuron;
    wire                  lti_spike_valid;
    wire                  lti_spike_ready;
    
    wire [DATA_WIDTH-1:0] lti_vitality_value;
    
    // 导出接口信号
    wire [DATA_WIDTH-1:0] lti_v_mem_export;
    wire [TIME_WIDTH-1:0] lti_last_spike_export;
    wire [DATA_WIDTH-1:0] lti_weight_export;
    wire [ADDR_WIDTH-1:0] lti_weight_addr;
    
    //=========================================================================
    // 组合逻辑：AXI-Lite 地址解码
    //=========================================================================
    wire write_en = s_axi_awvalid && s_axi_wvalid;
    wire read_en  = s_axi_arvalid && !rvalid_reg;
    
    wire [11:0] write_addr = s_axi_awaddr;
    wire [11:0] read_addr  = s_axi_araddr;
    
    // 导出接口地址检测
    wire export_write_en = write_en && (write_addr[11:10] == 2'b01);  // 0x400-0x7FF
    wire export_read_en  = read_en  && (read_addr[11:10]  == 2'b01);  // 0x400-0x7FF
    wire [7:0] export_offset = export_read_en ? read_addr[9:2] : write_addr[9:2];
    
    //=========================================================================
    // 时序逻辑：写操作
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_ctrl <= 32'h0;
            reg_time_mode <= 2'b0;
            reg_event_t1 <= 64'h0;
            reg_event_t2 <= 32'h0;
            reg_event_neuron <= 7'h0;
            reg_event_weight <= 16'h0;
            reg_vitality_id <= 7'h0;
            
            awready_reg <= 1'b0;
            wready_reg <= 1'b0;
            bresp_reg <= 2'b00;
            bvalid_reg <= 1'b0;
        end else begin
            // 默认状态
            awready_reg <= 1'b0;
            wready_reg <= 1'b0;
            
            // 写响应完成
            if (bvalid_reg && s_axi_bready) begin
                bvalid_reg <= 1'b0;
            end
            
            // 写操作
            if (write_en && !bvalid_reg) begin
                awready_reg <= 1'b1;
                wready_reg <= 1'b1;
                bvalid_reg <= 1'b1;
                bresp_reg <= 2'b00;  // OKAY
                
                case (write_addr)
                    REG_CTRL: begin
                        reg_ctrl <= s_axi_wdata;
                    end
                    REG_TIME_MODE: begin
                        reg_time_mode <= s_axi_wdata[1:0];
                    end
                    REG_EVENT_T1_HI: begin
                        reg_event_t1[63:32] <= s_axi_wdata;
                    end
                    REG_EVENT_T1_LO: begin
                        reg_event_t1[31:0] <= s_axi_wdata;
                    end
                    REG_EVENT_T2: begin
                        reg_event_t2 <= s_axi_wdata;
                    end
                    REG_EVENT_NEURON: begin
                        reg_event_neuron <= s_axi_wdata[6:0];
                    end
                    REG_EVENT_WEIGHT: begin
                        reg_event_weight <= s_axi_wdata[15:0];
                    end
                    REG_EVENT_TRIGGER: begin
                        // 触发事件，由组合逻辑处理
                    end
                    REG_VITALITY_ID: begin
                        reg_vitality_id <= s_axi_wdata[6:0];
                    end
                    // 导出接口写操作 (0x400-0x7FF)
                    default: begin
                        if (export_write_en) begin
                            case (export_offset)
                                EXPORT_CTRL: begin
                                    export_ctrl_reg <= s_axi_wdata;
                                    export_active <= s_axi_wdata[0];  // 启动导出
                                end
                                EXPORT_NEURON_ID: begin
                                    export_neuron_id_reg <= s_axi_wdata[6:0];
                                end
                                default: begin
                                    bresp_reg <= 2'b10;  // SLVERR
                                end
                            endcase
                        end else begin
                            bresp_reg <= 2'b10;  // SLVERR
                        end
                    end
                endcase
            end
        end
    end
    
    // 输出赋值
    assign s_axi_awready = awready_reg;
    assign s_axi_wready = wready_reg;
    assign s_axi_bresp = bresp_reg;
    assign s_axi_bvalid = bvalid_reg;

    //=========================================================================
    // 时序逻辑：读操作
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            arready_reg <= 1'b0;
            rdata_reg <= 32'h0;
            rresp_reg <= 2'b00;
            rvalid_reg <= 1'b0;
        end else begin
            arready_reg <= 1'b0;
            
            // 读响应完成
            if (rvalid_reg && s_axi_rready) begin
                rvalid_reg <= 1'b0;
            end
            
            // 读操作
            if (read_en && !rvalid_reg) begin
                arready_reg <= 1'b1;
                rvalid_reg <= 1'b1;
                rresp_reg <= 2'b00;  // OKAY
                
                case (read_addr)
                    REG_CTRL: rdata_reg <= reg_ctrl;
                    REG_STATUS: rdata_reg <= reg_status;
                    REG_TIME_MODE: rdata_reg <= {30'h0, reg_time_mode};
                    REG_EVENT_T1_HI: rdata_reg <= reg_event_t1[63:32];
                    REG_EVENT_T1_LO: rdata_reg <= reg_event_t1[31:0];
                    REG_EVENT_T2: rdata_reg <= reg_event_t2;
                    REG_EVENT_NEURON: rdata_reg <= {25'h0, reg_event_neuron};
                    REG_EVENT_WEIGHT: rdata_reg <= {16'h0, reg_event_weight};
                    REG_VITALITY_ID: rdata_reg <= {25'h0, reg_vitality_id};
                    REG_VITALITY_VALUE: rdata_reg <= {16'h0, lti_vitality_value};
                    REG_SPIKE_VALID: rdata_reg <= {31'h0, lti_spike_valid};
                    REG_SPIKE_NEURON: rdata_reg <= {25'h0, lti_spike_neuron};
                    REG_SPIKE_TIME_HI: rdata_reg <= lti_spike_time[63:32];
                    REG_SPIKE_TIME_LO: rdata_reg <= lti_spike_time[31:0];
                    REG_SPIKE_V_MEM: rdata_reg <= {16'h0, lti_spike_v_mem};
                    REG_VERSION: rdata_reg <= 32'h0001_0000;  // v1.0.0
                    
                    // 导出接口读操作 (0x400-0x7FF)
                    default: begin
                        if (export_read_en) begin
                            case (export_offset)
                                EXPORT_CTRL:       rdata_reg <= export_ctrl_reg;
                                EXPORT_STATUS:     rdata_reg <= export_status_reg;
                                EXPORT_NEURON_ID:  rdata_reg <= {25'h0, export_neuron_id_reg};
                                EXPORT_VITALITY:   rdata_reg <= {16'h0, lti_vitality_value};
                                EXPORT_V_MEM:      rdata_reg <= {16'h0, lti_v_mem_export};
                                EXPORT_LAST_SPIKE: rdata_reg <= lti_last_spike_export[31:0];
                                default: begin
                                    // 权重矩阵读取 (0x420-0x7FF)
                                    if (export_offset >= 8'h20 && export_offset < 8'h20 + N_NEURONS) begin
                                        rdata_reg <= {16'h0, lti_weight_export};
                                    end else begin
                                        rdata_reg <= 32'hDEAD_BEEF;
                                        rresp_reg <= 2'b10;  // SLVERR
                                    end
                                end
                            endcase
                        end else begin
                            rdata_reg <= 32'hDEAD_BEEF;
                            rresp_reg <= 2'b10;  // SLVERR
                        end
                    end
                endcase
            end
        end
    end
    
    // 输出赋值
    assign s_axi_arready = arready_reg;
    assign s_axi_rdata = rdata_reg;
    assign s_axi_rresp = rresp_reg;
    assign s_axi_rvalid = rvalid_reg;

    //=========================================================================
    // 状态寄存器更新
    //=========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            reg_status <= 32'h0;
        end else begin
            reg_status[0] <= lti_event_ready;   // 可接收事件
            reg_status[1] <= lti_spike_valid;   // 有脉冲输出
        end
    end
    
    //=========================================================================
    // 导出接口状态机
    //=========================================================================
    reg [ADDR_WIDTH-1:0] export_counter;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            export_state <= EXPORT_IDLE;
            export_status_reg <= 32'h0;
            export_counter <= 0;
        end else begin
            case (export_state)
                EXPORT_IDLE: begin
                    if (export_active) begin
                        export_state <= EXPORT_BUSY;
                        export_status_reg <= 32'h1;  // BUSY
                        export_counter <= 0;
                    end
                end
                
                EXPORT_BUSY: begin
                    // 导出进度计数
                    if (export_counter < N_NEURONS - 1) begin
                        export_counter <= export_counter + 1;
                    end else begin
                        export_state <= EXPORT_DONE;
                        export_status_reg <= 32'h2;  // DONE
                    end
                end
                
                EXPORT_DONE: begin
                    if (!export_active) begin
                        export_state <= EXPORT_IDLE;
                        export_status_reg <= 32'h0;
                    end
                end
                
                default: export_state <= EXPORT_IDLE;
            endcase
        end
    end
    
    // 权重地址生成
    assign lti_weight_addr = (export_state == EXPORT_BUSY) ? export_counter : export_neuron_id_reg;

    //=========================================================================
    // 事件触发逻辑
    //=========================================================================
    reg event_trigger_d;
    reg event_trigger_dd;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            event_trigger_d <= 1'b0;
            event_trigger_dd <= 1'b0;
        end else begin
            event_trigger_d <= (write_en && write_addr == REG_EVENT_TRIGGER);
            event_trigger_dd <= event_trigger_d;
        end
    end
    
    // 触发脉冲（一个时钟周期）
    wire event_trigger_pulse = event_trigger_d && !event_trigger_dd;

    //=========================================================================
    // 时间模式选择
    //=========================================================================
    assign lti_t1 = (reg_time_mode == 2'b00) ? reg_event_t1 : 64'h0;
    assign lti_t2_offset = (reg_time_mode == 2'b01) ? reg_event_t2 : 32'h0;
    
    //=========================================================================
    // LTI 核心实例化
    //=========================================================================
    assign lti_weight = reg_event_weight;
    assign lti_neuron_id = reg_event_neuron;
    assign lti_event_valid = event_trigger_pulse;
    assign lti_spike_ready = 1'b1;  // 始终准备接收脉冲

    lti_top #(
        .N_NEURONS(N_NEURONS),
        .DATA_WIDTH(DATA_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) lti_core (
        .clk(clk),
        .rst_n(rst_n && !reg_ctrl[0]),  // 软件复位
        
        // T3 同步接口
        .t3_sync_valid(1'b0),
        .t3_sync_value(64'h0),
        
        // 配置接口
        .cfg_time_mode(reg_time_mode),
        
        // 外部事件输入
        .s_axis_valid(lti_event_valid),
        .s_axis_neuron_id(lti_neuron_id),
        .s_axis_weight(lti_weight),
        .s_axis_t1(lti_t1),
        .s_axis_t2_offset(lti_t2_offset),
        .s_axis_ready(lti_event_ready),
        
        // 脉冲输出
        .m_axis_valid(lti_spike_valid),
        .m_axis_neuron_id(lti_spike_neuron),
        .m_axis_timestamp(lti_spike_time),
        .m_axis_v_mem(lti_spike_v_mem),
        .m_axis_ready(lti_spike_ready),
        
        // 活力查询
        .vitality_query_valid(1'b1),
        .vitality_query_id(reg_vitality_id),
        .vitality_query_value(lti_vitality_value),
        .vitality_query_ready(),
        
        // 导出接口
        .export_enable(export_active),
        .export_neuron_id(export_neuron_id_reg),
        .export_v_mem(lti_v_mem_export),
        .export_last_spike(lti_last_spike_export),
        .export_weight_addr(lti_weight_addr),
        .export_weight(lti_weight_export)
    );

    //=========================================================================
    // 中断输出
    //=========================================================================
    assign irq_event_ready = lti_event_ready;
    assign irq_spike_valid = lti_spike_valid;

endmodule
