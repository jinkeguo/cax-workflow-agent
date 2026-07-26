# SolidWorks Live Test Guide

This package does not include a proprietary `.SLDPRT` template. Use a disposable
copy of one of your own parts for write tests.

## 1. Environment detection

Start a new Codex task with the plugin enabled and ask:

```text
使用 cax-workflow-agent 检查我的 SolidWorks 环境。只检测，不打开或修改文件。
```

The Agent should call `get_solidworks_environment` and report the detected
SolidWorks executable, COM availability, PowerShell runtime, and configuration.

Then call `test_solidworks_connection`. A usable live connection must return
`status=succeeded`, `connection=ok`, and a non-empty SolidWorks revision. Registry
detection alone is not a successful communication test.

## 2. Read-only document inspection

Open or identify a disposable `.SLDPRT`, then ask:

```text
使用 inspect_solidworks_document 只读检查这个零件：
C:\path\to\disposable-part.SLDPRT
列出配置、特征、实体、包围盒和可参数化尺寸，不保存任何修改。
```

Confirm that the returned document path, document type, body count, feature
names, configurations, bounding box, and named dimensions match SolidWorks.

## 3. Template instantiation preview

Use fully qualified SolidWorks dimension names. First request a preview:

```text
以 disposable-template.SLDPRT 为模板创建 derived-part.SLDPRT。
把 D1@Sketch1 改为 100 mm、D1@Boss-Extrude1 改为 2 mm。
先预览，confirm_write=false，不要写文件。
```

Review the source, target, dimension names, values, and overwrite policy. Only
after they are correct, ask the Agent to repeat with `confirm_write=true`.
The adapter stages and rebuilds a copy; it must not modify the source template.

## 4. Neutral-format export

After reinspecting the derived part, export a new STEP or Parasolid file:

```text
把 derived-part.SLDPRT 导出为 derived-part.step。
先预览；确认目标不存在后再写入，并检查输出文件大小。
```

## Evidence to retain

For a useful first live-test report, retain:

- plugin version;
- SolidWorks version;
- returned `status`, `checks`, `warnings`, and `logs`;
- source and derived file timestamps;
- detected body count and bounding box;
- requested dimension names and final inspected values;
- rebuild/save/export error codes if a stage fails.

Do not test overwrite behavior on an authoritative engineering file.
