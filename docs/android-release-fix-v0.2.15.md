# ACMforever 0.2.15：草稿发布修复与重新首发

日期：2026-11-05。状态：修复提交评审，尚未创建 `v0.2.15` Tag，尚未发布公开安装包。客户端版本 `0.2.15` / `versionCode 29`，沿用当前 debug 渠道及原签名。

## 1. 已执行到哪里

- [PR #96](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/96) 已按用户明确指示合并，合并提交为 `5afd7588acfb864ea238881b5164523d3e048949`。
- `ANDROID_DEBUG_KEYSTORE_BASE64` 与 `ANDROID_RELEASE_CHANNEL=debug` 已配置；既有证书核对通过。
- `v0.2.14` 指向该合并提交，已触发 [首次发布 Action](https://github.com/GiraffesLoveBeauty/ACM-Forever/actions/runs/41941236889)。版本检查、30 项发布测试、Android 单测/Lint/编译、APK 与清单生成均已通过。
- Action 在上传草稿附件前失败；GitHub 留下空草稿 Release，未生成可匿名下载的公开版本，默认更新源仍不可用。该失败不能写作成功发布。
- 用户已选择改发 `0.2.15`，继续通过新 Tag 自动发布，不移动 `v0.2.14`，不手工上传 APK。

## 2. 根因与修复

首次失败为 `Only an unpublished draft may receive or replace assets`。服务器实际已创建草稿，但 `GET /releases/tags/v0.2.14` 在授权读取时仍返回 404；同一凭据读取 Releases 列表能找到 `tag_name=v0.2.14`、`draft=true` 的记录。

旧测试主要以 FakeGitHub 模拟“按 tag 总能找到草稿”，没有覆盖真实适配层的这项差异。本次先新增回归并在旧代码观察到失败，再进行修复。

- 按 Tag 查询返回 404 时，通过授权 Releases 列表分页精确匹配草稿的 `tag_name`；出现多个同 Tag 草稿就报错，避免任意覆盖。
- 草稿上传使用实际 Release ID；失败重试只替换同名草稿附件，不修改已公开版本。
- 附件回读使用附件 ID 和 `application/octet-stream`，二进制直接写文件；失败移除不完整文件，不把错误响应当作 APK。
- 公开操作按 Release ID 发 PATCH，并检查返回的 Tag 和草稿状态。GitHub CLI 负责认证传输，密钥和 Token 不写入日志。
- 继续逐件回读 APK、SHA-256 文件和 update.json，全部一致且版本仍递增后才公开。已公开版本保持不可覆盖，相同制品重跑不写入。
- App 递增为 `0.2.15/code29`，内置新增本版更新说明；更新交互和既有功能沿用 0.2.14。

## 3. 验证范围

本次发布测试为 38 项，包含 8 项新适配层回归：草稿 Tag 查询 404、列表分页、精确匹配、重复草稿拒绝、按 ID 上传及替换、二进制失败清理、按 ID 公开，以及通过真实 GitHub 适配类和模拟 gh 传输完成首发/不可变重跑。

本机 Android 69 项 JVM 单测通过，Lint 0 错误/53 警告，APK 构建通过；实际 APK 与内置 29 版日志、包名、版本、最低系统版本和原签名一致，实际制品更新清单生成成功。原有模拟器十三组验证属于 0.2.14 历史，本轮没有重复执行，不能写成本轮已完成的真机验收。

修复后的草稿查询逻辑还通过真实 GitHub 只读探针：按 Tag 读取 404 时，能从授权列表找到现有 0.2.14 空草稿，没有执行写操作。上传、公开和真实手机下载仍需本轮 PR 合并后的 Tag Action 验收。

本地包：`Android_APP/dist/acmforever-0.2.15-debug.apk`，2,069,392 字节；SHA-256 `5a0a42a47bb128abedac7588c69bdb67c53e044c436a6a847f3dfca95a7ed747`。证书 SHA-256 仍为 `88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4`。APK 和本机演练清单不进入 Git；Action 会从获准的 Tag 重新编译，最终公开 APK 的哈希以实际附件为准。

## 4. Review 关注点

本修复应交另一位成员或用户指定的 reviewer 检查，重点是：

1. 404 只触发草稿查找，403、网络错误等不能被吞掉。
2. 分页按精确 Tag 选择唯一草稿，不能覆盖其他 Tag 或已公开 Release。
3. 上传、回读和公开使用同一真实 Release/附件 ID；二进制下载不能被文本解码损坏。
4. 三件附件回读及二次最新版本检查通过前不公开；失败仍保留旧 latest。
5. 版本号、内置日志、Tag 和签名一致，code29 严格大于旧 code28。

本 PR 不修改网页、后端、数据库或服务器同步工作流，不为修复创建手工上传入口。

## 5. 评审合并后的首发步骤

1. 确认修复 PR 的当前 head 自动检查通过，并取得本轮 review 结论；不能沿用 PR #96 对旧脚本的无问题结论。
2. 合并修复 PR，确认 main 中 App 版本为 `0.2.15/code29`，debug 签名 Secret 和渠道配置仍正确。
3. 在获准的 main 提交创建并推送 `v0.2.15` Tag。保留原 `v0.2.14`，重跑它仍会使用旧源码，不能依靠重跑修复旧脚本。
4. 等待 `Android tag release` 成功。草稿内应有 `acmforever-0.2.15-debug.apk`、其 `.sha256` 和 `update.json`，回读核对后自动公开。
5. 匿名访问固定 `releases/latest/download/update.json`，确认 versionName 为 `0.2.15`、versionCode 为 `29`、channel 为 debug，APK URL 指向 v0.2.15。
6. 下载真实附件，检查大小、哈希、包名、实际版本、最低系统版本及原证书；在目标手机验收 code28 → code29 的提示、下载、系统确认及数据保留。

当前空的 0.2.14 草稿不会成为 latest，本次不修改或删除它，也不移动已经创建的 Tag。今后的正常发布仍使用“评审合并 → 新 Tag → Action 自动编译和发布”的流程。

相关文档：[android-tag-release-v0.2.14.md（原方案与工作流约束）](android-tag-release-v0.2.14.md)、[android-app.md（客户端说明）](android-app.md)。
