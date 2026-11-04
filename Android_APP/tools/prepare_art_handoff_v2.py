"""Repair the portable handoff prompt; package references, never generate artwork."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

repo = Path(__file__).resolve().parents[2]
pics = repo.parent / '图片'
canonical = repo / 'Android_APP/docs/猫娘分层素材制作与打包提示词.md'
old = pics / 'ACMforever_美术修改交接_v1'
new = pics / 'ACMforever_美术修改交接_v2'
text = canonical.read_text(encoding='utf-8')
instruction = '''零、先执行图像生成，不是让你改写提示词
这是实际绘图任务。请先读取我附带的三张参考图，然后立即调用你当前平台可用的图像生成或图像编辑模型，使用参考图进行重绘。必须真的调用绘图工具，而不是只在回答中说“调用”或复述这份要求。
如果平台有“创建图片 / 图像编辑 / image generation / image edit / imagegen”等工具，选择具备参考图输入能力的工具并把对应原图作为图像输入；准确工具名以你当前实际具备的工具为准，不假定某个供应商或模型已可用。
如果你是编程代理，先检查并遵循自己环境中的图像生成技能/工具说明；若有 imagegen 技能，按其实际流程调用底层图像模型。普通文件读写、Python、SVG、Canvas 或浏览器绘制不等于调用了图像模型。
不要用程序描摹原图、调整 HSV、手写 SVG、占位图、聊天里的图片链接或文字方案代替模型重绘。允许在真实模型生成之后用图形软件或代码做尺寸、透明背景、图层、遮罩、检查和 ZIP 整理。
如果确实没有图像模型/绘图工具，明确回复“当前环境没有可调用的图像生成/编辑工具，尚未生成图片”，列出缺少的能力并停止绘图阶段。不要假装已经画完，不要改成只输出另一份提示词，不要编造模型名、调用记录、文件或下载链接。
如果看不到参考图，先说明缺哪张，让使用者在对话里附上对应图片。朋友的 AI 不能读取我电脑上的 E: 路径；附带文件才是可用输入，不能因提示词写了路径就声称看过图片。

执行顺序：
阶段 A：先通过图像模型分别重绘头像、敲代码插画、剪影；每次输入对应原图并保持同一角色。实际保存三张生成图，直接展示图片供用户检查。不要只生成一张包含三幅图的拼贴，不要以生成提示词作为本阶段交付。
阶段 B：对通过检查的图进行精确分层和导出。若图像模型只能输出扁平图，请配合真正的图形编辑/分割工具；不能把扁平 PNG 换扩展名冒充 PSD，也不能把自动色相猜测当作准确图层。若缺少分层能力，保留已经实际生成的三张图并在 README 明确“已生成预览，尚未完成分层”，不要宣称整套交付完成。
阶段 C：验证文件、打包并交付真实 ZIP。平台若不能提供本机文件/ZIP，应给出已经实际生成的图片，并如实标记打包未完成，不能伪造下载地址。
在 README 中记录实际使用的平台、模型/工具（可见时）、本次是否实际调用、哪些文件为模型生成、哪些为后处理、哪些尚未完成。只记录真实可验证的信息，不要求泄露密钥或内部推理。

'''
instruction = instruction.replace('如果看不到参考图，先说明缺哪张，让使用者在对话里附上对应图片。', '如果已收到本交接 ZIP，先解压并读取其中的原图/1.png、原图/2.png、原图/3.png，不要重复索要已经在包内的原图。只有无法解压或确实缺图时，才说明缺哪张并请求单独附图。')
if '零、先执行图像生成' not in text:
    text = text.replace('一、参考图片', instruction + '一、参考图片', 1)
text = text.replace('以下整段可交给能够读写本地文件、绘图和导出素材的工具。', '修订版 v2：必须先实际调用参考图生成/编辑模型，再做分层与打包。请上传整个交接 ZIP，并发送下方完整任务。')
text = text.replace('请把三张原图附给具备绘图能力的 AI，并发送下方完整任务。', '请上传整个交接 ZIP，并发送下方完整任务。')
text = text.replace('如果看不到参考图，先说明缺哪张，让使用者在对话里附上对应图片。', '如果已收到本交接 ZIP，先解压并读取其中的原图/1.png、原图/2.png、原图/3.png，不要重复索要已经在包内的原图。只有无法解压或确实缺图时，才说明缺哪张并请求单独附图。')
text = text.replace('ACMforever_猫娘素材包_v1', 'ACMforever_猫娘素材包_v2')
canonical.write_text(text, encoding='utf-8')
new.mkdir(exist_ok=True)
for folder in ['原图', '效果参考']:
    shutil.copytree(old / folder, new / folder, dirs_exist_ok=True)
portable = text
for name in ['1.png', '2.png', '3.png']:
    portable = portable.replace(str(pics / name), f'原图/{name}')
portable = portable.replace(str(pics) + '\\', '')
(new / '完整制作提示词.md').write_text(portable, encoding='utf-8')
plain = portable.split('```text\n', 1)[1].rsplit('```', 1)[0].strip()
(new / '直接发给绘图AI.txt').write_text(plain, encoding='utf-8')
readme = '''# ACMforever 美术交接 v2

本包是参考原图与修订后的绘图任务，**不是已经重绘完成的素材**。

## 使用方法

1. 在具备图像生成/编辑能力的 AI 中开启图片工具；编程代理还需具备可用的绘图技能或模型。
2. 优先上传整个交接 ZIP，让 AI 解压后直接读取包内 `原图/1.png`、`原图/2.png`、`原图/3.png`。只有 AI 无法解压时才单独附上这三张图；无需重复上传包内原图。单给本机文件夹路径无效。
3. 发送 `直接发给绘图AI.txt` 的完整内容。它与 `完整制作提示词.md` 中的任务相同。
4. 要求先实际生成并展示三张重绘图，再进行分层、导出与 ZIP 打包。没有绘图工具的环境不能靠一句提示词获得工具能力。

## v2 修复了什么

v1 只强调“实际生成文件”，没有明确指定调用图像模型，因此编程 AI 可能用 SVG/Python 画图或只回制作方案。v2 新增明确的工具调用要求、三阶段交付、不可用时的停止条件与真实输出检查。它不保证任何平台都支持分层源文件或 ZIP；能力不足必须标明完成到哪一步。

`原图/1.png` 是头像；`原图/2.png` 是猫娘敲代码插画；`原图/3.png` 是剪影。`效果参考` 两图仅供外形补充与当前粗糙换色问题对照。

交回 `ACMforever_猫娘素材包_v2.zip`：包含真实生成图、可编辑分层源文件、原色/灰阶图层、精确遮罩、预览和 manifest。不能完成分层时先交真实预览并注明限制，不要冒充整包完成。App 接入及 APK 构建由本工程负责。
'''
(new / 'README-给朋友先看.md').write_text(readme, encoding='utf-8')
files = {p.relative_to(new).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in new.rglob('*') if p.is_file() and p.name != '文件校验.json'}
(new / '文件校验.json').write_text(json.dumps(files, ensure_ascii=False, indent=2), encoding='utf-8')
target = pics / 'ACMforever_美术修改交接_v2.zip'
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(new.rglob('*')):
        if path.is_file(): z.write(path, f'{new.name}/{path.relative_to(new).as_posix()}')
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert len({n.split('/')[0] for n in z.namelist()}) == 1
    packed = z.read(f'{new.name}/直接发给绘图AI.txt').decode('utf-8')
    assert '立即调用' in packed and '零、先执行图像生成' in packed and 'E:\\' not in packed
    for rel, digest in files.items(): assert hashlib.sha256(z.read(f'{new.name}/{rel}')).hexdigest() == digest
print(f'Validated handoff v2: {len(files)+1} files, {target.stat().st_size} bytes; references unchanged.')
