# Handoff — Evidence Copilot

> 新会话请先读此文件，再接上次的进度。

## 最后更新

2026-08-31

## 当前进度

MVP 已推到 GitHub：**https://github.com/LawrenceLiu2005/MedCopilot**（`main`）。云端 Secrets 读取已接入代码。

**Streamlit Community Cloud 应用尚未创建完成**：需要你用 GitHub 在浏览器登录授权（我这边不能替你输入 GitHub 密码）。一键部署页：

https://share.streamlit.io/deploy?repository=LawrenceLiu2005/MedCopilot&branch=main&mainModule=app.py

登录后 Main file 选 `app.py`，Secrets 填 `NCBI_EMAIL`（可选 `NCBI_API_KEY`）。

## 本次做了什么

- 初始化 Git，首次提交并推送；`.env`、`.data/`、`.streamlit/secrets.toml` 未入库
- NCBI 邮箱/Key 增加 Streamlit Secrets 读取，便于上线后不用本地 `.env`
- 离线+联网测试 **80 passed**；演示主题 E2E（二甲双胍 RCT）**1 passed**
- 本机 `streamlit run app.py` 页面可打开（http://localhost:8501）

## 下一次建议做什么

1. 用 GitHub 登录上面的 Streamlit 部署页，创建应用并填 Secrets
2. 打开得到的 `*.streamlit.app` 网址，点「填入示例检索」走一遍
3. 把下面「发给导师」的三段话 + 网址发给导师

## 你需要知道的事

- 发给导师时说明：试用稿请挑别扭处；建议点「填入示例检索」；重要操作请导出；尽量不要两人同时猛用同一网址
- 关掉页面或云端重启后，筛过的记录可能丢失
- 不要用 Vercel / 不要做 dmg

## 阻塞 / 待你提供

- [ ] 在浏览器完成 Streamlit Cloud 的 GitHub 登录与 Deploy（约 2 分钟）
- [ ] 把生成的 `*.streamlit.app` 网址补进发给导师的消息

**命令**：

```bash
pip install -r requirements.txt
streamlit run app.py
pytest -v
```
