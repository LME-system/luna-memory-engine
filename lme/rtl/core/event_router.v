//=============================================================================
// Module: event_router
// Description: 异步事件路由网络，支持优先级和时间戳排序
// Author: Luna Project
// Date: 2026-03-24
//=============================================================================

`timescale 1ns / 1ps

module event_router #(
    parameter N_INPUTS = 4,             // 输入端口数
    parameter N_OUTPUTS = 4,            // 输出端口数 (LIF/STDP/DG/CA3)
    parameter FIFO_DEPTH = 32,          // 每输入FIFO深度
    parameter TIME_WIDTH = 32,
    parameter DATA_WIDTH = 16,
    parameter ADDR_WIDTH = 7
)(
    // 系统接口
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire                     ce,
    
    // 路由表配置 (256神经元 → 4输出)
    input  wire [1:0]               route_table [0:127],
    
    // 输入事件接口
    input  wire [N_INPUTS-1:0]      in_valid,
    input  wire [N_INPUTS*ADDR_WIDTH-1:0] in_neuron_id,
    input  wire [N_INPUTS*DATA_WIDTH-1:0] in_weight,
    input  wire [N_INPUTS*TIME_WIDTH-1:0] in_timestamp,
    output wire [N_INPUTS-1:0]      in_ready,
    
    // 输出事件接口
    output reg  [N_OUTPUTS-1:0]     out_valid,
    output reg  [N_OUTPUTS*ADDR_WIDTH-1:0] out_neuron_id,
    output reg  [N_OUTPUTS*DATA_WIDTH-1:0] out_weight,
    output reg  [N_OUTPUTS*TIME_WIDTH-1:0] out_timestamp,
    input  wire [N_OUTPUTS-1:0]     out_ready,
    
    // 状态输出
    output wire [N_INPUTS*6-1:0]    fifo_fill_level   // 每FIFO填充数
);

    //=========================================================================
    // 输入FIFO (每输入一个)
    //=========================================================================
    
    localparam FIFO_ADDR_WIDTH = 5;  // log2(32)
    
    // FIFO存储
    reg [ADDR_WIDTH-1:0] fifo_neuron [0:N_INPUTS-1][0:FIFO_DEPTH-1];
    reg [DATA_WIDTH-1:0] fifo_weight [0:N_INPUTS-1][0:FIFO_DEPTH-1];
    reg [TIME_WIDTH-1:0] fifo_time [0:N_INPUTS-1][0:FIFO_DEPTH-1];
    
    reg [FIFO_ADDR_WIDTH:0] fifo_wr_ptr [0:N_INPUTS-1];
    reg [FIFO_ADDR_WIDTH:0] fifo_rd_ptr [0:N_INPUTS-1];
    
    wire [FIFO_ADDR_WIDTH:0] fifo_count [0:N_INPUTS-1];
    wire fifo_empty [0:N_INPUTS-1];
    wire fifo_full [0:N_INPUTS-1];
    
    genvar g;
    generate
        for (g = 0; g < N_INPUTS; g = g + 1) begin : gen_fifo_status
            assign fifo_count[g] = fifo_wr_ptr[g] - fifo_rd_ptr[g];
            assign fifo_empty[g] = (fifo_count[g] == 0);
            assign fifo_full[g] = (fifo_count[g] == FIFO_DEPTH);
            assign in_ready[g] = !fifo_full[g];
            assign fifo_fill_level[g*6 +: 6] = fifo_count[g][5:0];
        end
    endgenerate
    
    //=========================================================================
    // FIFO写入逻辑
    //=========================================================================
    
    integer i;
    
    always @(posedge clk) begin
        for (i = 0; i < N_INPUTS; i = i + 1) begin
            if (in_valid[i] && in_ready[i]) begin
                fifo_neuron[i][fifo_wr_ptr[i][FIFO_ADDR_WIDTH-1:0]] <= 
                    in_neuron_id[i*ADDR_WIDTH +: ADDR_WIDTH];
                fifo_weight[i][fifo_wr_ptr[i][FIFO_ADDR_WIDTH-1:0]] <= 
                    in_weight[i*DATA_WIDTH +: DATA_WIDTH];
                fifo_time[i][fifo_wr_ptr[i][FIFO_ADDR_WIDTH-1:0]] <= 
                    in_timestamp[i*TIME_WIDTH +: TIME_WIDTH];
                fifo_wr_ptr[i] <= fifo_wr_ptr[i] + 1;
            end
        end
    end
    
    //=========================================================================
    // 优先级仲裁: 时间戳排序 (寻找最老的事件)
    //=========================================================================
    
    reg [TIME_WIDTH-1:0] min_timestamp;
    reg [2:0] selected_input;  // log2(4) = 2, 扩展为3位
    reg found_valid;
    
    // 组合逻辑: 寻找最小时间戳
    always @(*) begin
        min_timestamp = {TIME_WIDTH{1'b1}};
        selected_input = 0;
        found_valid = 0;
        
        for (i = 0; i < N_INPUTS; i = i + 1) begin
            if (!fifo_empty[i]) begin
                if (fifo_time[i][fifo_rd_ptr[i][FIFO_ADDR_WIDTH-1:0]] < min_timestamp) begin
                    min_timestamp = fifo_time[i][fifo_rd_ptr[i][FIFO_ADDR_WIDTH-1:0]];
                    selected_input = i[2:0];
                    found_valid = 1;
                end
            end
        end
    end
    
    //=========================================================================
    // 路由输出逻辑
    //=========================================================================
    
    reg [ADDR_WIDTH-1:0] routed_neuron;
    reg [DATA_WIDTH-1:0] routed_weight;
    reg [TIME_WIDTH-1:0] routed_time;
    reg [1:0] target_output;
    
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_valid <= 0;
            
            for (i = 0; i < N_INPUTS; i = i + 1) begin
                fifo_rd_ptr[i] <= 0;
            end
            
        end else if (ce) begin
            // 默认无效
            out_valid <= 0;
            
            if (found_valid) begin
                // 读取选中的FIFO
                routed_neuron <= fifo_neuron[selected_input][fifo_rd_ptr[selected_input][FIFO_ADDR_WIDTH-1:0]];
                routed_weight <= fifo_weight[selected_input][fifo_rd_ptr[selected_input][FIFO_ADDR_WIDTH-1:0]];
                routed_time <= fifo_time[selected_input][fifo_rd_ptr[selected_input][FIFO_ADDR_WIDTH-1:0]];
                
                // 查找路由目标
                target_output <= route_table[routed_neuron];
                
                // 检查目标是否就绪
                if (out_ready[target_output]) begin
                    // 输出事件
                    out_valid[target_output] <= 1;
                    out_neuron_id[target_output*ADDR_WIDTH +: ADDR_WIDTH] <= routed_neuron;
                    out_weight[target_output*DATA_WIDTH +: DATA_WIDTH] <= routed_weight;
                    out_timestamp[target_OUTPUT*TIME_WIDTH +: TIME_WIDTH] <= routed_time;
                    
                    // 更新读指针
                    fifo_rd_ptr[selected_input] <= fifo_rd_ptr[selected_input] + 1;
                end
            end
        end
    end

endmodule
