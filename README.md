# 留守儿童情绪手账分析系统使用手册

本项目用于乡村支教场景下的儿童情绪手账辅助分析。系统支持上传儿童手账图片，自动识别图片文字，提取颜色、明暗、留白、线条密度等图像线索，并调用讯飞 Spark 生成情绪状态分析、性格倾向画像、教育建议和 Word 报告。

> 重要说明：本系统只用于支教老师日常观察和心理健康关怀辅助，不构成心理诊断或医学诊断。如发现孩子持续低落、自伤自杀言论、攻击行为或其他高风险表现，应及时联系监护人、学校心理教师或专业人员。

## 一、运行环境

推荐环境：

- Windows 10 或 Windows 11
- Python 3.10 或以上
- Edge 或 Chrome 浏览器
- 讯飞开放平台账号
- 已开通 Spark X2/X1.5 HTTP 服务

当前版本使用 Windows 本地 OCR，因此最适合在 Windows 电脑上运行。

## 二、下载项目

打开终端或 PowerShell，运行：

```powershell
git clone https://github.com/kexuan141-tech/analysis.git
cd analysis
```

如果没有安装 Git，也可以在 GitHub 页面点击 `Code` -> `Download ZIP`，下载后解压。

## 三、安装依赖

进入项目目录后运行：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

如果下载速度慢，可以使用清华镜像：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 四、配置自己的讯飞 API 密钥

项目里有一个 `.env.example` 文件。先复制一份并改名为 `.env`：

```powershell
copy .env.example .env
```

然后用记事本或 VS Code 打开 `.env`，填入自己的讯飞信息：

```env
XUNFEI_APP_ID=你的APPID
XUNFEI_API_KEY=你的APIKey
XUNFEI_API_SECRET=你的APISecret
XUNFEI_API_PASSWORD=你的HTTP服务APIPassword
```

注意：

- 每个队友都要使用自己的 API 信息。
- `.env` 不能上传 GitHub，也不要发给别人。
- `XUNFEI_API_PASSWORD` 要填 HTTP 服务认证信息，不是 WebSocket 的 APISecret。

## 五、启动系统

在项目目录中运行：

```powershell
streamlit run app.py
```

启动后浏览器会自动打开：

```text
http://localhost:8501
```

如果没有自动打开，把终端里显示的网址复制到浏览器即可。

## 六、基本使用流程

1. 在左侧填写孩子基本信息：
   - 姓名
   - 年龄
   - 性别
   - 年级
2. 选择星火大模型版本，默认使用 `Spark X2`。
3. 上传儿童情绪手账图片。
4. 可选：在补充描述里写明画面主题、颜色、孩子当时状态等。
5. 点击 `开始分析`。
6. 查看分析结果：
   - 概览
   - 性格画像
   - 情绪分析
   - 教育建议
   - 报告下载
7. 在 `报告下载` 页面下载 Word 报告。

## 七、上传图片建议

为了提高 OCR 和图像分析准确率，建议：

- 正对纸面拍摄；
- 不要倾斜太多；
- 避免阴影、反光、模糊；
- 手账文字尽量清楚；
- 图片里尽量只包含手账页面，不要截到电脑界面、侧栏或其他无关内容；
- 如果 OCR 识别不准，可以在补充描述里手动写出孩子写的文字。

## 八、Word 报告包含什么

下载的 Word 报告会包含：

- 学生基本信息
- 图片内容识别
- 情绪状态分析
- 性格特征画像
- 行为倾向预测
- 教育建议
- 风险评估
- 情绪雷达图
- 情绪分布分析图

报告可用于支教成果材料整理，但不能作为心理诊断材料。

## 九、常见问题

### 1. 点不了“开始分析”

请先确认是否已经上传图片。当前系统设置为：只要上传图片，就可以开始分析，姓名不是必填。

### 2. API 调用失败

检查 `.env` 文件：

- 是否已经复制 `.env.example` 并改名为 `.env`；
- `XUNFEI_API_PASSWORD` 是否填写正确；
- 讯飞平台是否开通 Spark X2/X1.5 HTTP 服务；
- 账号 token 余额是否充足；
- 网络是否能访问讯飞接口。

### 3. OCR 识别不准确

优先换更清晰的照片。也可以在“补充描述”中手动填写孩子写下的文字，系统会结合补充描述进行分析。

### 4. Word 报告里没有图

请重新点击 `开始分析`，分析完成后再下载 Word 报告。旧报告不会自动更新。

### 5. 队友能不能访问我的电脑上的系统？

如果在同一个 Wi-Fi 下，可以用局域网访问。

你启动时运行：

```powershell
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

队友访问：

```text
http://你的局域网IP:8501
```

如果打不开，可能是 Windows 防火墙拦截，需要允许 Python/Streamlit 通过防火墙。

## 十、项目文件说明

```text
app.py                  主程序入口
requirements.txt        Python 依赖
.env.example            API 密钥配置模板
utils/analyzer.py       情绪分析、图表、Word 报告生成
utils/ocr.py            OCR 调用和文字清洗
utils/windows_ocr.ps1   Windows 本地 OCR 脚本
队友部署说明.md          部署说明
analysis_method_basis.docx 分析依据与方法说明
```

## 十一、隐私和安全提醒

- 不要上传真实儿童隐私图片到公开仓库。
- 不要把 `.env` 上传到 GitHub。
- 不要公开分享 API 密钥。
- 报告只用于支教辅助观察，不要给孩子贴标签。
- 高风险情况要及时联系专业人员。

