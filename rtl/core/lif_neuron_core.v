//=============================================================================
// Module: lif_neuron_core
// Description: 128-LIF神经元阵列，事件驱动，PYNQ-Z2优化
// Author: Luna Project
// Date: 2026-03-24
//=============================================================================

`timescale 1ns / 1ps

module lif_neuron_core #(
    parameter N_NEURONS = 128,          // PYNQ-Z2优化: 128神经元
    parameter DATA_WIDTH = 16,          // Q8.8定点数
    parameter TIME_WIDTH = 32,          // 微秒时间戳
    parameter ADDR_WIDTH = 7            // log2(128)
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     ce,             // 时钟使能
    
    // 配置接口 (AXI-Lite)
    input  wire [DATA_WIDTH-1:0]    cfg_tau_mem,    // 膜时间常数 (默认: 20.0 = 0x1400)
    input  wire [DATA_WIDTH-1:0]    cfg_v_th,       // 发放阈值 (默认: 1.0 = 0x100)
    input  wire [DATA_WIDTH-1:0]    cfg_v_reset,    // 重置电位 (默认: 0.0 = 0x000)
    input  wire [15:0]              cfg_tau_ref,    // 不应期 (微秒)
    
    // 事件输入接口 (AXI-Stream)
    input  wire                     s_axis_valid,
    input  wire [ADDR_WIDTH-1:0]    s_axis_neuron_id,
    input  wire [DATA_WIDTH-1:0]    s_axis_weight,
    input  wire [TIME_WIDTH-1:0]    s_axis_timestamp,
    output wire                     s_axis_ready,
    
    // 脉冲输出接口 (AXI-Stream)
    output reg                      m_axis_valid,
    output reg [ADDR_WIDTH-1:0]     m_axis_neuron_id,
    output reg [TIME_WIDTH-1:0]     m_axis_timestamp,
    output reg [DATA_WIDTH-1:0]     m_axis_v_mem,   // 发放时的膜电位
    input  wire                     m_axis_ready,
    
    // 状态输出 (调试)
    output wire [DATA_WIDTH-1:0]    dbg_v_mem [0:N_NEURONS-1],
    output wire [TIME_WIDTH-1:0]    dbg_last_spike [0:N_NEURONS-1]
);

    //=========================================================================
    // 内部信号
    //=========================================================================
    
    // 神经元状态存储 (分布式RAM)
    reg [DATA_WIDTH-1:0] v_mem [0:N_NEURONS-1];
    reg [TIME_WIDTH-1:0] last_spike_time [0:N_NEURONS-1];
    reg refractory [0:N_NEURONS-1];
    
    // 泄漏因子计算: alpha = 1 - dt/tau
    // 简化: dt=1ms固定, alpha = 256 - 256/tau
    wire [DATA_WIDTH-1:0] leak_alpha;
    assign leak_alpha = {8'd1, 8'd0} - ({8'd1, 8'd0} / cfg_tau_mem[15:8]);
    
    // 状态机
    localparam IDLE = 3'b000;
    localparam READ = 3'b001;
    localparam UPDATE = 3'b010;
    localparam CHECK = 3'b011;
    localparam SPIKE = 3'b100;
    localparam RESET = 3'b101;
    
    reg [2:0] state;
    reg [ADDR_WIDTH-1:0] current_neuron;
    reg [DATA_WIDTH-1:0] current_weight;
    reg [TIME_WIDTH-1:0] current_time;
    
    // 临时计算
    reg [DATA_WIDTH-1:0] v_new;
    reg in_refractory;
    reg [TIME_WIDTH-1:0] time_since_spike;
    
    integer i;
    
    //=========================================================================
    // 调试输出
    //=========================================================================
    generate
        genvar g;
        for (g = 0; g < N_NEURONS; g = g + 1) begin : gen_debug
            assign dbg_v_mem[g] = v_mem[g];
            assign dbg_last_spike[g] = last_spike_time[g];
        end
    endgenerate
    
    //=========================================================================
    // 主状态机
    //=========================================================================
    
    assign s_axis_ready = (state == IDLE);
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            m_axis_valid <= 0;
            
            // 初始化神经元状态
            for (i = 0; i < N_NEURONS; i = i + 1) begin
                v_mem[i] <= 0;
                last_spike_time[i] <= 0;
                refractory[i] <= 0;
            end
            
        end else if (ce) begin
            case (state)
                IDLE: begin
                    m_axis_valid <= 0;
                    
                    if (s_axis_valid && s_axis_ready) begin
                        current_neuron <= s_axis_neuron_id;
                        current_weight <= s_axis_weight;
                        current_time <= s_axis_timestamp;
                        state <= READ;
                    end
                end
                
                READ: begin
                    // 检查不应期
                    time_since_spike <= current_time - last_spike_time[current_neuron];
                    state <= UPDATE;
                end
                
                UPDATE: begin
                    in_refractory <= (time_since_spike < cfg_tau_ref);
                    
                    if (!in_refractory) begin
                        // 泄漏积分: v = v * alpha + I
                        // Q8.8乘法: (v * alpha) >> 8
                        v_new <= ((v_mem[current_neuron] * leak_alpha) >> 8) + current_weight;
                    end else begin
                        v_new <= v_mem[current_neuron]; // 不应期内不更新
                    end
                    
                    state <= CHECK;
                end
                
                CHECK: begin
                    v_mem[current_neuron] <= v_new;
                    
                    // 检查发放
                    if (!in_refractory && v_new >= cfg_v_th) begin
                        state <= SPIKE;
                    end else begin
                        state <= IDLE;
                    end
                end
                
                SPIKE: begin
                    // 输出脉冲
                    m_axis_valid <= 1;
                    m_axis_neuron_id <= current_neuron;
                    m_axis_timestamp <= current_time;
                    m_axis_v_mem <= v_mem[current_neuron];
                    
                    if (m_axis_ready || !m_axis_valid) begin
                        state <= RESET;
                    end
                end
                
                RESET: begin
                    // 重置膜电位
                    v_mem[current_neuron] <= cfg_v_reset;
                    last_spike_time[current_neuron] <= current_time;
                    refractory[current_neuron] <= 1;
                    
                    m_axis_valid <= 0;
                    state <= IDLE;
                end
                
                default: state <= IDLE;
            endcase
        end
    end

endmodule
