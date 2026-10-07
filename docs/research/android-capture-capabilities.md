# 调研：Android 旧手机定时采集能力（Tasker / Automate / MacroDroid）

> Issue: #3 ｜ 分支: `research/android-capture` ｜ 调研日期: 2026-10-07
> 方法：全部结论基于 curl 抓取的官方一手文档（Tasker 官方 userguide、LlamaLab Automate 官方文档、MacroDroid 官方 wiki、Android 开发者文档、Syncthing 官方仓库）。社区实测帖（Reddit / Tasker 论坛）本次被反爬拦截，相关项已明确标注「未验证/未查到」。

## 结论速览（TL;DR）

1. **能实现**。Tasker（Time Context 每 1-3 分钟重复 + Take Photo action，官方均支持，且 Take Photo 有 Discreet 模式可息屏静拍）；Automate 更强，`Take picture` 和 `Video record`（可限时 5-11s）都是官方 block；MacroDroid 官方 wiki 也列有 Take Picture / Record Video action。
2. **主要敌人是 Doze + 厂商杀后台**：Doze 会推迟普通定时器、挂起网络；必须用 Allow-While-Idle 类闹钟 + 电池优化白名单 + 厂商专项设置（dontkillmyapp.com）。
3. **电耗/发热社区实测数据：未查到**（Reddit r/Tasker 与 Tasker 官方论坛搜索均被反爬拦截）。官方文档仅给出定性结论。建议 24h 自测。
4. **同步到 Mac 首选 Syncthing**，但注意官方 Android 客户端 2024-12 已停更归档，应改用活跃维护的 **Syncthing-Fork**（F-Droid 可装，官方提供迁移文档）。
5. **版本分水岭**：6.0（Doze）→ 12（精确闹钟需用户授权）→ 14（前台服务必须声明类型，camera/dataSync 等）→ 15（开机自启后相机/麦克风默认禁用，Automate 官方文档明确提及）。**旧手机（≤Android 11）反而是限制最少的理想采集端**。

---

## 1. 每 1-3 分钟定时拍照 / 录 5-11s 短片：能否实现？

**结论：三个工具都能做到定时拍照；录像首选 Automate（原生 block 支持限时录制），Tasker 无内置录像 action。**

### Tasker
- **定时**：Time Context 原生支持 Repeat——「first occurrence is at From Time and then **every X hours or minutes** until End Time」。
  来源：https://tasker.joaoapps.com/userguide/en/timecontext.html
- **拍照**：Take Photo action，官方文档确认：
  - 有 **Discreet** 选项：「no visible or audible sign of the picture being taken, and **the device will not turn on if it is already off**」——即支持息屏静拍；
  - 输出 JPG 到 `/sdcard/dcim/Tasker/`，支持 Series（序号）/ Chronological（时间戳）命名。
  来源：https://tasker.joaoapps.com/userguide/en/help/ah_take_photo.html
- **录像**：Tasker 官方帮助文件目录（抓取于 2026-10-07）中**没有**内置录视频 action（仅有 `ah_take_photo.html`、`ah_take_screenshot.html` 等；无 take_video）。录视频需走第三方插件或 camera intent（第三方方案，本次未逐一验证）。
  来源：https://tasker.joaoapps.com/userguide/en/help/ （目录列表）
- **典型配置**：Profile = Time（From 07:00 To 23:00，Repeat every 1 minute）→ Task = Take Photo（Discreet ✓, 前置/后置可选）+ 后续同步 action。

### Automate（LlamaLab）
- **拍照**：`Take picture` block，官方文档确认存在。
  来源：https://llamalab.com/automate/doc/block/index.html （block 索引含 take_picture）
- **录像**：`Video record` + `Video record stop` block，官方文档原文：「An action block that records video... **The recording can be limited to a maximum duration and/or maximum file size**, it can also be stopped with a Video record stop block or by cancelling the notification」——正好覆盖「录 5-11 秒短片」的需求。
  来源：https://llamalab.com/automate/doc/block/video_record_start.html
- **重要坑（官方文档原文）**：若 flow 随系统自启，在 **Android 14+** 上 flow 可能无法访问麦克风，**Android 15+** 上无法访问相机，直到 App 被手动启动过一次（除非授予「appear on top」悬浮窗权限）。
  来源：同上 video_record_start 页
- **定时**：`Time await` / `Time window` block + 循环可实现任意间隔（block 索引可见）。

### MacroDroid
- 官方 wiki 的 Actions 页面列出 **Take Picture** 和 **Record Video** 两个 action。
  来源：https://wiki.macrodroid.com/wiki/index.php/Actions

---

## 2. 息屏/锁屏后台保活：Doze 与电池优化的限制

**结论：普通定时器在 Doze 下会被推迟到 maintenance window；核心对策 = Allow-While-Idle 精确闹钟 + 电池优化白名单 + 厂商专项设置。**

### Android Doze 的官方规则（developer.android.com）
设备静止息屏且未充电时进入 Doze：
- **挂起网络访问**、**忽略 wake lock**；
- **推迟标准 AlarmManager 闹钟**（含 `setExact()`、`setWindow()`）到下一个 maintenance window；
- 例外：`setAndAllowWhileIdle()` / `setExactAndAllowWhileIdle()` 可在 Doze 中触发；`setAlarmClock()` 闹钟前系统会短暂退出 Doze；
- maintenance window 随时间**越来越稀疏**（省电）；
- 用户亮屏/移动设备/插充电器 → 立即退出 Doze。
  来源：https://developer.android.com/training/monitoring-device-state/doze-standby?hl=en

### Tasker 官方的说法（一手）
- 「Starting with **Android 5.0**, many devices will act aggressively to try and save system battery power... Tasker may not function as expected」；典型症状就是「profiles with **Time contexts don't activate** at the expected time」；官方给出的对策清单 + 按厂商查 **dontkillmyapp.com**。
  来源：https://tasker.joaoapps.com/userguide/en/androidpowermanagement.html
- Tasker 自身定时用 AlarmManager，其可靠触发依赖上述机制（官方电源管理页引申，具体 alarm 实现细节未在公开文档中展开——**此句为推断，未逐条验证**）。

### 精确闹钟权限收紧（Android 12+）
- target 12+ 必须声明 `SCHEDULE_EXACT_ALARM` 并取得用户授予的「Alarms & reminders」特殊权限；**target 13+ 的新装 App 默认不预授予**；备份恢复到 14 的设备该权限会被拒。
  来源：https://developer.android.com/training/scheduling/alarms?hl=en

### 社区实测经验
- **未查到（本次被拦截）**：r/Tasker（reddit.com JSON 接口返回非 JSON 反爬页）、Tasker 官方论坛（forum.joaoapps.com 的 search.json 返回 404/空，2026-10-07 抓取）。无法引用具体实测帖。
- 但 Tasker 官方电源管理页背书的 **dontkillmyapp.com** 是社区公认的厂商杀后台对策索引（小米/华为/三星等各家步骤），可作为操作指南入口。
  来源：https://dontkillmyapp.com/ （经 Tasker 官方页引用）

### 实操清单（由以上官方文档推导）
1. 采集 App 设为电池优化「不优化」（Doze 白名单）。
2. 需要分钟级准时 → 用精确闹钟（Tasker 的 AlarmManager 路径 / Automate 的 time block），并在系统设置授予「闹钟和提醒」特殊权限（Android 12+）。
3. 按机型查 dontkillmyapp.com 关闭厂商激进出管（自启管理、后台弹窗、省电策略锁定）。
4. 常插电运行可完全绕开 Doze（插充电器即退出 Doze——官方规则）。

---

## 3. 连续运行一天的电耗与发热

**结论：未查到可引用的社区实测数字（Reddit / Tasker 论坛本次均被反爬拦截，无法核验具体帖子的数据）。**

- 官方一手文档只给定性结论：Doze 的存在本身就说明「长时间息屏后台活动」是被系统重点抑制的对象（developer.android.com Doze 页，见上节来源）。
- Tasker 官方未公布任何电耗基准数据（userguide 无相关页面，抓取于 2026-10-07）。
- **建议自测方案（未验证，供后续执行）**：旧手机跑 Tasker 每 2 分钟 Take Photo 24h，记录起始/结束电量；或 `adb bugreport` 用 Battery Historian 看唤醒次数；用 Tasker `%BATT` 变量每小时 log 电量。把结果回填到本文档。
- 定性预期（推断，非实测）：每 1-3 分钟一次的拍照涉及相机唤醒 + 存储 IO，Doze 会被频繁打断，电耗显著高于纯息屏待机；常插电 + 去掉手机壳可同时解决电耗与发热问题（无来源，工程判断）。

---

## 4. 照片自动同步到 Mac

**结论：首选 Syncthing（Syncthing-Fork on Android + Mac 官方 Syncthing），同网段点对点直连、无需公网；注意官方 Android 客户端已停更。**

### Syncthing Android 客户端现状（关键事实）
- **官方 `syncthing-android` 已停止开发**：仓库 README 原文「This app is discontinued. The last release on Github and F-Droid will happen with the **December 2024** Syncthing version... the entire repo will be archived」。原因：Google Play 发布政策 + 无人维护。
  来源：https://github.com/syncthing/syncthing-android （README）
- **替代品：Syncthing-Fork**（原 Catfriend1 维护，现 researchxxl org），活跃维护，F-Droid 包名 `com.github.catfriend1.syncthingfork`，提供从官方版迁移的 wiki 文档。
  来源：https://github.com/Catfriend1/syncthing-android （README：「Switching from the deprecated official version — See our wiki article」）

### 配置要点（基于官方文档 + 上述仓库）
1. **Android 端装 Syncthing-Fork**（F-Droid），Mac 端 `brew install syncthing` 或官方发行包（Syncthing 官网/文档：https://docs.syncthing.net/ ）。
2. **同一 Wi-Fi 下互配设备**：Syncthing 是点对点同步，同网段走 LAN 直连，不经公网（官方文档 https://docs.syncthing.net/ ）。
3. **Doze 影响同步**：Doze 挂起网络（见第 2 节），意味着息屏时同步窗口受限——把 Syncthing-Fork 加入电池优化白名单；或让采集端常插电（插电即退出 Doze，官方规则）。
4. **单向发送**：Android 目录（如 `/sdcard/dcim/Tasker/`）设 Send Only，Mac 端 Receive Only，避免回写冲突（Syncthing 通用配置原则，见官方文档 FAQ/介绍页）。
5. **Android 13+ 照片权限**：App 访问照片需要媒体权限（SAF/READ_MEDIA_IMAGES），Syncthing-Fork 处理方式见其 wiki——**此点未逐页核验**（wiki 页面本次抓取 404），装好后实测为准。
6. 备选：网盘中转（iCloud/坚果云/Google Drive 客户端自动上传）可靠性也可行，但旧手机上后台保活同样受第 2 节限制，且引入第三方信任；**未做横向实测**。

---

## 5. Android 版本差异：后台限制收紧时间线

**结论：6.0（Doze）→ 9/10（厂商激进省电成标配）→ 12（精确闹钟需授权）→ 14（前台服务必须声明类型）→ 15（开机自启后相机/麦克风默认禁用）。做采集端，版本越老限制越少。**

| 版本 | 变化 | 来源 |
|---|---|---|
| Android 5.0 | 厂商开始激进省电，后台自动化工具可靠性下降（Tasker 官方口径） | https://tasker.joaoapps.com/userguide/en/androidpowermanagement.html |
| Android 6.0 (API 23) | 引入 **Doze + App Standby**：息屏静止时挂起网络、推迟闹钟/JobScheduler（官方 Doze 文档，见第 2 节） | https://developer.android.com/training/monitoring-device-state/doze-standby?hl=en |
| Android 10 | `foregroundServiceType` 属性引入（Android 14 强制的前置铺垫） | https://developer.android.com/about/versions/14/changes/fgs-types-required?hl=en （文中注明「Android 10 introduced the android:foregroundServiceType attribute」） |
| Android 12 (API 31) | 精确闹钟需 `SCHEDULE_EXACT_ALARM` + 用户授权「Alarms & reminders」；到期闹钟不受前台服务启动限制影响 | https://developer.android.com/training/scheduling/alarms?hl=en |
| Android 13 (API 33) | 新装 App 默认**不预授予**精确闹钟权限 | 同上 |
| Android 14 (API 34) | 前台服务**必须声明类型**（camera / dataSync / mediaPlayback 等），否则 `MissingForegroundServiceTypeException`；各类型还需声明对应新权限；无匹配类型场景官方建议迁到 WorkManager | https://developer.android.com/about/versions/14/changes/fgs-types-required?hl=en |
| Android 15 | 开机自启的 App 在被手动启动前**无法访问相机/麦克风**（除非有悬浮窗权限）——Automate 官方文档明确记录此坑 | https://llamalab.com/automate/doc/block/video_record_start.html |

**对选型的含义**：家里的旧手机若是 Android 8-11，恰好落在「有 Doze 但没有 12+ 精确闹钟授权 / 14+ FGS 类型 / 15 相机自启限制」的窗口，是自动化采集阻力最小的版本段；Android 6-7 也能用，但厂商 ROM 老旧杀后台行为更野（dontkillmyapp.com 按机型排查）。

---

## 未完成 / 未验证清单（诚实披露）

| 项 | 状态 | 原因 |
|---|---|---|
| r/Tasker、Tasker 官方论坛的电耗/发热实测数字 | 未查到 | Reddit 与 forum.joaoapps.com 的搜索接口被反爬拦截（2026-10-07） |
| Tasker 第三方录视频插件的具体推荐 | 未验证 | Tasker 无官方录像 action；插件生态未逐一测试 |
| Syncthing-Fork wiki 具体页面（run conditions 等） | 未核验 | wiki 原文抓取 404，仅引用了 README |
| MacroDroid Take Picture / Record Video 参数细节 | 未展开 | 官方 wiki Actions 页确认存在，参数页未抓 |
