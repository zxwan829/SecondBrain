# VNext 工作台本地预览

这是 Issue #260 的隔离合成原型。它只展示本地演示内容，不请求 `/api`，也不会创建 AI 会话或写入 Core。

## 启动

在 macOS Finder 双击 `启动VNext工作台预览.command`。终端服务绑定 `127.0.0.1:4182`，不会自动打开浏览器。手动访问：

`http://127.0.0.1:4182/vnext.html`

停止时在终端按 `Ctrl+C`。也可从本目录运行 `npm run dev:vnext`。需要先按仓库锁文件安装前端依赖；此原型新增依赖为零。

## 当前范围

- 首屏默认卡片为今日待办、待审核和项目进度；“添加卡片”可加入最近知识，卡片可通过上/下按钮调整顺序。
- 待办使用合成字段展示计划日期、可选截止日期、提醒、重要度和逾期，并支持本地勾选及撤销。
- 页面针对桌面、平板和手机断点布局；没有天气 API 时明确显示未接入，不显示假天气。
- `/chat` 链接保留现有新对话入口的导航目标，但预览不发请求、不创建会话。

卡片顺序和待办状态目前仅保存在页面内存中，刷新会重置；这是首版静态/交互结构验证，不是可保存的个性化工作台。真实 Task DTO 目前没有计划日期、独立提醒和重要度字段；接入真实数据前须另行审查并批准 API/schema 方案。

## 验证

在 `web-app/secondbrain-frontend` 运行：

```sh
npm run typecheck
npm test -- src/vnext-workbench.test.tsx
npm run build:vnext
```

此预览使用单独 Vite 配置和独立构建输出 `dist-vnext-workbench/`，不加载开发 API 代理。未进行浏览器 GUI 验收或 macOS Playwright 测试。
