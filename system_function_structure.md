# 系统功能结构说明

结合当前仓库实现，系统整体是一个以 `Django` 为核心的医疗 AI Web 应用，前台提供翻译、问答、历史记录与知识库页面，后台承载接口、知识库管理、模型调用和数据持久化。

## 技术栈概览

| 层级 | 当前技术栈 | 说明 |
| --- | --- | --- |
| 前端展示层 | `Django Templates`、`HTML`、`CSS`、`JavaScript` | 提供首页、翻译页、问答页、历史页、登录注册页、知识库管理页 |
| Web 服务层 | `Django 4.2`、`Django REST Framework`、`JWT` | 提供页面路由、API 接口、登录鉴权、业务编排 |
| 业务应用层 | `accounts`、`translation`、`qa`、`history`、`feedback`、`audit`、`kb` | 负责用户、翻译、问答、知识库、反馈、审计等模块 |
| AI 能力层 | `Transformers`、`PEFT/LoRA`、`sentence-transformers`、`FAISS`、`OpenAI SDK` | 负责本地翻译、向量检索、RAG 问答、外部模型调用 |
| 数据存储层 | `MySQL`、知识库文件、模型目录、上传文件目录 | 存储业务数据、知识库索引、训练产物、上传文档 |
| 训练与数据处理层 | `scripts/` 下训练与构建脚本 | 用于 LoRA 微调、知识库多语言构建、训练数据生成与评估 |


## 系统总体架构图

```mermaid
flowchart TB
    USER[普通用户]
    ADMIN[管理员]

    subgraph CLIENT[表现层]
        PAGE[Web 页面\nhome / translate / qa / history / kb]
    end

    subgraph SERVER[应用服务层]
        ROUTER[路由与接口入口\nDjango URLConf + DRF]
        AUTH[认证鉴权\nJWT + Session]
        TRANS[翻译服务\ntranslation]
        QA[问答服务\nqa]
        KB[知识库服务\nkb]
        SUPPORT[支撑模块\naccounts / history / feedback / audit]
    end

    subgraph AI[AI 能力层]
        NLLB[本地翻译模型\nNLLB + LoRA]
        RAG[RAG 检索\nBGE-M3 + FAISS]
        LLM[问答生成模型\nSiliconFlow / Qwen]
    end

    subgraph DATA[数据资源层]
        MYSQL[(MySQL)]
        KBSTORE[知识库索引与实体文件\nchunks / entities / faiss.index]
        MODELSTORE[本地模型文件\nhuggingface/ + scripts/models/]
        UPLOADS[上传文档\nkb_uploads/]
        TRAINDATA[训练与语料数据\nbackend/data/]
    end

    subgraph OFFLINE[离线构建层]
        JOBS[训练与构建脚本\nbuild_multilang / generate_training_data / train_lora]
    end

    USER --> PAGE
    ADMIN --> PAGE

    PAGE --> ROUTER
    ROUTER --> AUTH
    ROUTER --> TRANS
    ROUTER --> QA
    ROUTER --> KB
    ROUTER --> SUPPORT

    TRANS --> NLLB
    TRANS --> MYSQL

    QA --> RAG
    QA --> LLM
    QA --> MYSQL

    KB --> MYSQL
    KB --> KBSTORE
    KB --> UPLOADS

    SUPPORT --> MYSQL

    NLLB --> MODELSTORE
    RAG --> KBSTORE

    KB --> JOBS
    JOBS --> TRAINDATA
    JOBS --> MODELSTORE
    JOBS --> KBSTORE
```

## 系统业务流程图

```mermaid
flowchart TB
    START([开始])
    LOGIN[用户登录 / 进入系统]
    HOME[进入首页并选择功能]

    CHOICE{选择业务功能}

    TRANS_IN[输入待翻译文本\n选择源语言和目标语言]
    TRANS_RUN[调用翻译服务\nNLLB + LoRA 生成结果]
    TERM[术语识别与术语卡片匹配]
    TRANS_OUT[展示翻译结果\n保存翻译记录]

    QA_IN[输入医学问题]
    RETRIEVE[检索知识库\nRAG 召回相关内容]
    GENERATE[调用问答模型生成回答]
    QA_OUT[展示问答结果与来源\n保存问答记录]

    KB_UPLOAD[上传文本或文档]
    KB_PARSE[解析内容并抽取候选实体]
    KB_REVIEW{管理员审核}
    KB_SAVE[写入知识库实体库]
    KB_BUILD[构建多语言知识库/训练数据]

    HISTORY[查看历史记录]
    FEEDBACK[提交反馈或纠错]
    AUDIT[记录审计日志]
    END([结束])

    START --> LOGIN --> HOME --> CHOICE

    CHOICE -->|医疗翻译| TRANS_IN
    TRANS_IN --> TRANS_RUN --> TERM --> TRANS_OUT --> HISTORY

    CHOICE -->|医疗问答| QA_IN
    QA_IN --> RETRIEVE --> GENERATE --> QA_OUT --> HISTORY

    CHOICE -->|知识库管理| KB_UPLOAD
    KB_UPLOAD --> KB_PARSE --> KB_REVIEW
    KB_REVIEW -->|通过| KB_SAVE --> KB_BUILD
    KB_REVIEW -->|驳回| KB_UPLOAD

    CHOICE -->|查看历史| HISTORY
    CHOICE -->|提交反馈| FEEDBACK

    TRANS_OUT --> FEEDBACK
    QA_OUT --> FEEDBACK

    TRANS_OUT --> AUDIT
    QA_OUT --> AUDIT
    KB_BUILD --> AUDIT
    FEEDBACK --> AUDIT

    HISTORY --> END
    FEEDBACK --> END
    AUDIT --> END
    KB_BUILD --> END
```

## 翻译模块结构图

```mermaid
flowchart TB
    U[用户输入]

    U --> IN[输入处理层\n文本内容 / 源语言 / 目标语言 / 领域参数]
    IN --> API[翻译接口层\ntranslation.views.TranslateView]

    API --> CORE[翻译业务层\n参数校验 / 任务编排 / 响应封装]
    API --> TERMEX[术语抽取层\nterm_matcher]

    CORE --> MODEL[模型调用层\ntranslator_hf]
    MODEL --> BASE[基础模型\nNLLB-200]
    MODEL --> LORA[微调适配器\nLoRA]

    TERMEX --> KBMATCH[术语匹配与解释检索\nKB 检索 / 术语卡片构建]

    CORE --> TASK[(翻译任务记录\nTranslationTask / MySQL)]
    KBMATCH --> KBFILE[知识库资源\nentities.json / chunks.json / faiss.index]

    BASE --> OUT[翻译结果输出\nbase_translation]
    LORA --> OUT2[增强翻译结果输出\nlora_translation]

    OUT --> RESP[结果返回层]
    OUT2 --> RESP
    KBMATCH --> RESP
    TASK --> RESP

    RESP --> VIEW[前端展示\n翻译结果 + 术语卡片 + 延迟信息]
```

## 问答模块流程图

```mermaid
flowchart TB
    START([开始])
    INPUT[用户输入医学问题\n选择回答语言]
    API[问答接口\nqa.views.QAView]
    CHECK{问题是否有效}

    RETRIEVE[检索知识库\nget_kb().search top_k]
    CONTEXT[整理召回结果\n构建上下文与来源列表]
    JUDGE{是否检索到有效上下文}

    LLM[调用问答生成模型\nSiliconFlow / Qwen]
    FALLBACK[返回默认兜底回答]

    ANSWER[生成最终回答]
    SAVE[保存问答记录\nQATask / Session]
    AUDIT[写入审计日志]
    OUTPUT[返回答案、置信度、来源、耗时]
    END([结束])

    START --> INPUT --> API --> CHECK
    CHECK -->|否| FALLBACK
    CHECK -->|是| RETRIEVE --> CONTEXT --> JUDGE

    JUDGE -->|否| FALLBACK
    JUDGE -->|是| LLM --> ANSWER

    FALLBACK --> ANSWER
    ANSWER --> SAVE --> AUDIT --> OUTPUT --> END
```

## 知识库管理模块图

```mermaid
flowchart TB
    USER[普通用户]
    ADMIN[管理员]

    USER --> UPLOAD[知识上传入口\n文本输入 / 文件上传]
    ADMIN --> DASHBOARD[知识库管理后台]

    UPLOAD --> RAW[原始资料存储\nRawKBUpload]
    DASHBOARD --> LIST[上传记录 / 候选实体 / 知识条目查看]

    RAW --> EXTRACT[内容解析与候选实体抽取\nextract_text + extract_candidate_payloads]
    EXTRACT --> CANDIDATE[候选实体池\nCandidateEntity]

    DASHBOARD --> REVIEW{管理员审核}
    CANDIDATE --> REVIEW

    REVIEW -->|通过| ENTITY[知识实体入库\nKBEntity + TermCard]
    REVIEW -->|驳回| REJECT[候选实体驳回]
    REVIEW -->|修改后通过| EDIT[编辑候选实体]
    EDIT --> ENTITY

    ENTITY --> TRANS[多语言知识翻译\ntranslate_kb_entity]
    ENTITY --> BUILD[知识库构建\nbuild_multilang]
    ENTITY --> TRAIN[训练数据生成\ngenerate_training_data]

    BUILD --> KBFILE[知识库文件输出\nentities.json / chunks.json / faiss.index]
    TRAIN --> TRAINDATA[训练语料输出\nbackend/data/]

    RAW --> DB[(MySQL)]
    CANDIDATE --> DB
    ENTITY --> DB
    REJECT --> DB

    DASHBOARD --> AUDIT[审计与操作留痕]
    ENTITY --> AUDIT
    BUILD --> AUDIT
```

## 历史记录与结果管理模块图

```mermaid
flowchart TB
    USER[用户]

    USER --> TRANSRES[翻译结果页]
    USER --> QARES[问答结果页]
    USER --> HISTORYPAGE[历史记录页]

    TRANSRES --> TRANSSTORE[翻译结果存储\nTranslationTask]
    QARES --> QASTORE[问答结果存储\nQATask]

    TRANSSTORE --> HISTORYAPI[历史记录查询与展示\nhistory 模块]
    QASTORE --> HISTORYAPI

    HISTORYPAGE --> HISTORYAPI
    HISTORYAPI --> DB[(MySQL)]

    HISTORYAPI --> RESULTVIEW[结果展示与回溯\n按时间 / 类型 / 用户查看]

    RESULTVIEW --> FEEDBACK[反馈与纠错提交\nfeedback 模块]
    FEEDBACK --> FEEDSTORE[反馈信息存储\nFeedback]
    FEEDSTORE --> DB

    TRANSSTORE --> AUDIT[操作审计\nAuditLog]
    QASTORE --> AUDIT
    FEEDSTORE --> AUDIT
    AUDIT --> DB
```

## 四、说明

从当前系统实现情况看，翻译与问答是核心功能，术语识别与知识库是支撑功能，医疗文本解析与预约挂号属于增强功能。系统采用模块化设计，各功能之间既可以独立使用，也可以相互联动，形成“翻译 - 术语解释 - 知识问答 - 历史追踪 - 后台维护”的完整闭环。

