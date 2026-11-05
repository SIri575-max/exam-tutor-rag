# 本机资料配置

工作台默认在本机运行。仓库里的小样例可以单独运行，完整功能依赖使用者自己的本地资料。

1. 将 `textbook_source_config.example.json` 复制为 `textbook_source_config.json`。将 `source_config.example.json` 复制为 `source_config.json`。填写有权使用的教材和讲义路径。
2. 运行 `python sync_sources.py --config textbook_source_config.json` 登记教材，运行 `python sync_sources.py` 登记讲义。读取原页需要 Poppler，完整题图识别需要独立的 `.venv-ocr` 和 `requirements-ocr.txt`。
3. 用 `organize_full_book.ps1` 生成本机教材档案。目录映射、页码和题目切分按原型所用的教材版次配置，使用其他版次时先核对并调整 `book_structure.py`。
4. 在 `.venv-rag` 中运行 `download_embedding.py` 准备 BGE 模型。可用 `exercise_vectors.py` 建立索引，再用 `question_knowledge.py` 构建本地知识网络。工作区已有评估脚本需要对应版本的本机题干和标签。
5. 启动 `start_demo.ps1`。需要生成讲解时，复制 `.env.example` 为 `.env`，在本机配置模型服务和密钥。

OCR 数据、图片、向量和人工审核记录默认写到 `data/private/`。样例题评估与本机教材评估分开运行。660B 原型数据处理以源 PDF 哈希识别版本，使用其他扫描件时需重新确定题干范围和章节边界。
