//=============================================================================
// Module: dg_pattern_separation
// Description: DG-like稀疏编码与WTA竞争，Top-K选择
// Author: Luna Project
// Date: 2026-03-24
//=============================================================================

`timescale 1ns / 1ps

module dg_pattern_separation #(
    parameter INPUT_DIM = 512,          // 输入维度 (PYNQ-Z2优化)
    parameter OUTPUT_DIM = 1024,        // 输出维度 (DG展开)
    parameter SPARSITY_K = 20,          // Top-K (1024 * 0.02)
    parameter DATA_WIDTH = 16,
    parameter TIME_WIDTH = 32
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     ce,
    
    // 配置
    input  wire [DATA_WIDTH-1:0]    cfg_threshold,    // 发放阈值
    input  wire [DATA_WIDTH-1:0]    cfg_inhibition,   // 抑制强度
    
    // 输入向量 (AXI-Stream)
    input  wire                     s_axis_valid,
    input  wire [DATA_WIDTH-1:0]    s_axis_data,
    output wire                     s_axis_ready,
    input  wire                     s_axis_last,      // 帧结束
    
    // 输出脉冲 (AXI-Stream)
    output reg                      m_axis_valid,
    output reg [9:0]                m_axis_neuron_id,  // log2(1024)
    output reg [DATA_WIDTH-1:0]     m_axis_potential,
    output reg [TIME_WIDTH-1:0]     m_axis_timestamp,
    input  wire                     m_axis_ready,
    output reg                      m_axis_last,
    
    // 稀疏编码输出 (BRAM接口)
    output reg [DATA_WIDTH-1:0]     sparse_code [0:OUTPUT_DIM-1],
    output reg                      sparse_code_valid
);

    //=========================================================================
    // 随机投影矩阵 (只读，存储在BRAM)
    // 使用LFSR生成伪随机投影，节省存储
    //=========================================================================
    
    reg [15:0] lfsr;
    wire [DATA_WIDTH-1:0] projection_value;
    
    // LFSR生成伪随机数
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr <= 16'hACE1;
        end else begin
            lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[14] ^ lfsr[12] ^ lfsr[3]};
        end
    end
    
    assign projection_value = {lfsr[7:0], 8'b0};  // Q8.8格式
    
    //=========================================================================
    // 输入缓冲与矩阵乘法
    //=========================================================================
    
    reg [DATA_WIDTH-1:0] input_buffer [0:INPUT_DIM-1];
    reg [9:0] input_count;
    reg input_ready;
    
    // 输出电位累加
    reg [DATA_WIDTH-1:0] potentials [0:OUTPUT_DIM-1];
    reg potentials_valid;
    
    // 状态机
    localparam IDLE = 3'b000;
    localparam LOAD = 3'b001;
    localparam COMPUTE = 3'b010;
    localparam INHIBIT = 3'b011;
    localparam SELECT = 3'b100;
    localparam OUTPUT = 3'b101;
    
    reg [2:0] state;
    reg [9:0] compute_i;  // 输入索引
    reg [9:0] compute_j;  // 输出索引
    
    //=========================================================================
    // Top-K选择器 (简化版: 阈值+排序)
    //=========================================================================
    
    reg [9:0] selected_neurons [0:SPARSITY_K-1];
    reg [DATA_WIDTH-1:0] selected_potentials [0:SPARSITY_K-1];
    reg [4:0] selected_count;
    
    // 比较与交换网络 (简化Bubble Sort)
    reg [9:0] sort_neuron [0:SPARSITY_K-1];
    reg [DATA_WIDTH-1:0] sort_potential [0:SPARSITY_K-1];
    
    integer idx, jdx;
    
    //=========================================================================
    // 主状态机
    //=========================================================================
    
    assign s_axis_ready = (state == LOAD) && (input_count < INPUT_DIM);
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            input_count <= 0;
            m_axis_valid <= 0;
            sparse_code_valid <= 0;
            
            for (idx = 0; idx < OUTPUT_DIM; idx = idx + 1) begin
                potentials[idx] <= 0;
                sparse_code[idx] <= 0;
            end
            
        end else if (ce) begin
            case (state)
                IDLE: begin
                    m_axis_valid <= 0;
                    sparse_code_valid <= 0;
                    input_count <= 0;
                    
                    if (s_axis_valid) begin
                        state <= LOAD;
                    end
                end
                
                LOAD: begin
                    // 加载输入向量
                    if (s_axis_valid && s_axis_ready) begin
                        input_buffer[input_count] <= s_axis_data;
                        input_count <= input_count + 1;
                        
                        if (s_axis_last || input_count >= INPUT_DIM-1) begin
                            compute_i <= 0;
                            compute_j <= 0;
                            state <= COMPUTE;
                        end
                    end
                end
                
                COMPUTE: begin
                    // 矩阵乘法: 逐输入累加
                    if (compute_i < input_count) begin
                        // 使用LFSR生成投影权重
                        reg [DATA_WIDTH-1:0] proj;
                        proj = projection_value;
                        
                        // 累加: potential[j] += input[i] * proj
                        if (compute_j < OUTPUT_DIM) begin
                            potentials[compute_j] <= potentials[compute_j] + 
                                ((input_buffer[compute_i] * proj) >> 8);
                            compute_j <= compute_j + 1;
                        end else begin
                            compute_j <= 0;
                            compute_i <= compute_i + 1;
                        end
                    end else begin
                        state <= INHIBIT;
                    end
                end
                
                INHIBIT: begin
                    // 横向抑制: 全局均值抑制
                    reg [DATA_WIDTH+9:0] sum_potential;
                    reg [DATA_WIDTH-1:0] mean_potential;
                    
                    sum_potential = 0;
                    for (idx = 0; idx < OUTPUT_DIM; idx = idx + 1) begin
                        sum_potential = sum_potential + potentials[idx];
                    end
                    mean_potential = sum_potential[DATA_WIDTH+9:10];  // 除以1024
                    
                    // 应用抑制
                    for (idx = 0; idx < OUTPUT_DIM; idx = idx + 1) begin
                        if (potentials[idx] > mean_potential) begin
                            potentials[idx] <= potentials[idx] - 
                                ((cfg_inhibition * mean_potential) >> 8);
                        end
                    end
                    
                    selected_count <= 0;
                    state <= SELECT;
                end
                
                SELECT: begin
                    // Top-K选择 (简化: 阈值+前K个)
                    selected_count <= 0;
                    
                    for (idx = 0; idx < OUTPUT_DIM && selected_count < SPARSITY_K; idx = idx + 1) begin
                        if (potentials[idx] > cfg_threshold) begin
                            selected_neurons[selected_count] <= idx[9:0];
                            selected_potentials[selected_count] <= potentials[idx];
                            sparse_code[idx] <= potentials[idx];
                            selected_count <= selected_count + 1;
                        end else begin
                            sparse_code[idx] <= 0;
                        end
                    end
                    
                    sparse_code_valid <= 1;
                    selected_count <= 0;
                    state <= OUTPUT;
                end
                
                OUTPUT: begin
                    // 输出脉冲事件
                    if (selected_count < SPARSITY_K) begin
                        m_axis_valid <= 1;
                        m_axis_neuron_id <= selected_neurons[selected_count];
                        m_axis_potential <= selected_potentials[selected_count];
                        m_axis_timestamp <= 0;  // 由上层填充
                        m_axis_last <= (selected_count == SPARSITY_K-1);
                        
                        if (m_axis_ready) begin
                            selected_count <= selected_count + 1;
                        end
                    end else begin
                        m_axis_valid <= 0;
                        state <= IDLE;
                    end
                end
                
                default: state <= IDLE;
            endcase
        end
    end

endmodule
