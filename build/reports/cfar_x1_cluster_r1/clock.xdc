create_clock -name module_clk -period 6.666667 [get_ports aclk]
set_input_delay -clock module_clk 0 [get_ports -filter {DIRECTION == IN && NAME != aclk}]
set_output_delay -clock module_clk 0 [get_ports -filter {DIRECTION == OUT}]
