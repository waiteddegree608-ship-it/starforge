# Starforge

用 **OpenCode + DeepSeek Flash** 循环寻找真实需求、实现小工具、检查并发布。目标是提高做出有用开源项目的效率；不会制造 star，也不保证增长。

流程：免费读取公开 GitHub Issues → 要求至少两条真实需求依据 → 生成标准库 Python CLI、测试和中英文 README → 静态检查和第二轮模型审查 → 候选分支 CI → 通过后发布独立源码预览仓库。

默认每 6 小时扫描，每天最多发布 1 个原型。没有好候选就跳过；失败需求会记录，避免反复花钱重做。当前会记录已有项目的 star、fork、issue 数，但还没有根据历史数据自动预测增长的功能。

## 本地运行

详见 [英文配置指南](README.md)。需要 Python 3.10+、OpenCode、GitHub 凭据和 DeepSeek Key。

```powershell
Copy-Item config.example.json config.local.json
# 修改目录、GitHub 用户名、OpenCode 可执行文件路径和价格核对日期
python -m starforge --config config.local.json probe
python -m starforge --config config.local.json loop
```

`probe` 会发起一次很小的真实付费请求。查看状态、暂停下一轮或恢复：

```powershell
python -m starforge --config config.local.json status
python -m starforge --config config.local.json pause
python -m starforge --config config.local.json resume
```

预算每天最高 ¥20，按香港时间重置。每次调用前先预留保守费用，成功后按 API token 使用量结算；网络结果不明时保留预留金额并停止，不盲目重试。预算按峰值单价、保守货币换算和余量计算，是控制器估算，不是服务商账单。配置单价七天后过期，必须核实价格才继续。其他软件的消费不计入此控制器。

真正的 API Key 留在父进程；OpenCode 只能访问本轮候选目录，不能执行 Shell、操作 GitHub 或改预算。生成代码只在 GitHub 临时 Runner 中执行。候选分支在测试前是公开的，但明确标为未发布，正式原型仓库必须通过检查后才创建。

Windows 可使用当前账户绑定的 DPAPI 加密文件；配置、凭据、生成记录和日志放在仓库外。循环不会修改 EKina/Paperfect，不会删除仓库，也不会自动向别人发推广消息。模型审查和测试不等于人工验收，第一版只支持小型离线 Python 工具。

源码采用 MIT；第三方工具和 API 保留各自许可与服务条款。
