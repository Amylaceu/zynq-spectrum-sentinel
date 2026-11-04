# LCD界面集成协作记录

需求：固定PL及四色接口，实现信号、目标、统计与状态栏，保留v2回退。

问题及纠正：第一次板测因Pillow7无textlength卡住；改用兼容字形度量。第二次绘制性能不足，受控提前停止。第三次采用有界字形缓存并保留完整计时口径。

G2第三轮600.929秒完成，785次提交零错误，最低38.965fps；用户确认画面正常。UI总耗时中位36.108ms/P95 165.069ms，未达25/40ms，记FAIL（功能PASS），不增加第四轮。最终停止GPIO/SRC/audio=0，冻结LCD驱动/位流未变。证据board/measurements/g2_acceptance_final.json及SHA256，原始目录g2_monitor_r3_raw。G3进入协议/服务开发，尚未部署；配置A授权保持，无发射。

软件回归664 passed/18 skipped。实际TX高亮未发射验收，不以离线预览替代。
