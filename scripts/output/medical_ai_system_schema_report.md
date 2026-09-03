# 数据库结构导出报告

生成时间：2026-03-31T19:54:42

该报告来自真实数据库结构，可直接作为数据库设计说明书的辅助素材。

## 1. 数据库环境

| 项目 | 值 |
| --- | --- |
| Django 数据源 | default |
| 数据库名 | medical_ai_system |
| 数据库引擎 | django.db.backends.mysql |
| 主机 | 127.0.0.1 |
| 端口 | 3306 |
| 字符集 | utf8mb4 |
| 时区 | UTC |
| 表数量 | 18 |

## 2. 数据表列表

| 序号 | 表名 | 类型 | 来源模型 | 分类 | 预估行数 | 表注释 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | accounts_userprofile | table | accounts.UserProfile | 业务表 | 3 | - |
| 2 | audit_auditlog | table | audit.AuditLog | 业务表 | 65 | - |
| 3 | auth_group | table | auth.Group | 系统表 | 2 | - |
| 4 | auth_group_permissions | table | - | 系统表 | 54 | - |
| 5 | auth_permission | table | auth.Permission | 系统表 | 62 | - |
| 6 | auth_user | table | auth.User | 系统表 | 4 | - |
| 7 | auth_user_groups | table | - | 系统表 | 2 | - |
| 8 | auth_user_user_permissions | table | - | 系统表 | 0 | - |
| 9 | django_admin_log | table | admin.LogEntry | 系统表 | 13 | - |
| 10 | django_content_type | table | contenttypes.ContentType | 系统表 | 16 | - |
| 11 | django_migrations | table | - | 系统表 | 30 | - |
| 12 | django_session | table | sessions.Session | 系统表 | 2 | - |
| 13 | feedback_feedback | table | feedback.Feedback | 业务表 | 11 | - |
| 14 | kb_kbentity | table | kb.KBEntity | 业务表 | 1 | - |
| 15 | kb_rawkbupload | table | kb.RawKBUpload | 业务表 | 8 | - |
| 16 | kb_termcard | table | kb.TermCard | 业务表 | 5 | - |
| 17 | qa_qatask | table | qa.QATask | 业务表 | 98 | - |
| 18 | translation_translationtask | table | translation.TranslationTask | 业务表 | 262 | - |

## 3. 数据表详情

> 注：MySQL `TABLE_ROWS` 对 InnoDB 通常是估算值，可用于文档参考，但不应当作为精确统计口径。

### 3.1 accounts_userprofile

- 表类型：table
- 来源模型：accounts.UserProfile
- 分类：业务表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：3
- 表注释：-
- 创建时间：2026-03-30 02:22:10
- 最近更新时间：2026-03-30 06:30:42

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | phone | varchar(20) | - | - | - | - | - | - | - |
| 3 | gender | varchar(1) | - | - | - | - | - | - | - |
| 4 | age | int | Y | - | - | - | - | - | - |
| 5 | occupation | varchar(100) | - | - | - | - | - | - | - |
| 6 | department | varchar(100) | - | - | - | - | - | - | - |
| 7 | hospital | varchar(200) | - | - | - | - | - | - | - |
| 8 | bio | longtext | - | - | - | - | - | - | - |
| 9 | avatar_url | varchar(500) | - | - | - | - | - | - | - |
| 10 | created_at | datetime(6) | - | - | - | - | - | - | - |
| 11 | updated_at | datetime(6) | - | - | - | - | - | - | - |
| 12 | user_id | int | - | - | - | Y | - | - | - |
| 13 | role | varchar(16) | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| user_id | BTREE | Y | - | user_id | A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| accounts_userprofile_user_id_92240672_fk_auth_user_id | user_id | auth_user | id |

### 3.2 audit_auditlog

- 表类型：table
- 来源模型：audit.AuditLog
- 分类：业务表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：65
- 表注释：-
- 创建时间：2026-03-03 09:34:41
- 最近更新时间：2026-03-31 01:34:39

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | action | varchar(128) | - | - | - | - | - | - | - |
| 3 | method | varchar(16) | - | - | - | - | - | - | - |
| 4 | path | varchar(512) | - | - | - | - | - | - | - |
| 5 | status_code | int | Y | - | - | - | - | - | - |
| 6 | ip | varchar(64) | - | - | - | - | - | - | - |
| 7 | user_agent | varchar(512) | - | - | - | - | - | - | - |
| 8 | request_id | varchar(64) | - | - | - | - | - | - | - |
| 9 | latency_ms | int | Y | - | - | - | - | - | - |
| 10 | extra | json | - | - | - | - | - | - | - |
| 11 | created_at | datetime(6) | - | - | - | - | - | - | - |
| 12 | user_id | int | Y | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| audit_audit_action_766c6d_idx | BTREE | - | - | action, created_at | A, A |
| audit_audit_request_06fe30_idx | BTREE | - | - | request_id | A |
| audit_audit_user_id_a3c2bc_idx | BTREE | - | - | user_id, created_at | A, A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| audit_auditlog_user_id_c1cca96c_fk_auth_user_id | user_id | auth_user | id |

### 3.3 auth_group

- 表类型：table
- 来源模型：auth.Group
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：2
- 表注释：-
- 创建时间：2026-02-24 05:01:36

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | int | - | - | Y | - | Y | auto_increment | - |
| 2 | name | varchar(150) | - | - | - | Y | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| name | BTREE | Y | - | name | A |

#### 外键信息

无外键信息。

### 3.4 auth_group_permissions

- 表类型：table
- 来源模型：-
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：54
- 表注释：-
- 创建时间：2026-02-24 05:01:35

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | group_id | int | - | - | - | - | - | - | - |
| 3 | permission_id | int | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| auth_group_permissio_permission_id_84c5c92e_fk_auth_perm | BTREE | - | - | permission_id | A |
| auth_group_permissions_group_id_permission_id_0cd325b0_uniq | BTREE | Y | - | group_id, permission_id | A, A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| auth_group_permissio_permission_id_84c5c92e_fk_auth_perm | permission_id | auth_permission | id |
| auth_group_permissions_group_id_b120cbf9_fk_auth_group_id | group_id | auth_group | id |

### 3.5 auth_permission

- 表类型：table
- 来源模型：auth.Permission
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：62
- 表注释：-
- 创建时间：2026-02-24 05:01:36

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | int | - | - | Y | - | Y | auto_increment | - |
| 2 | name | varchar(255) | - | - | - | - | - | - | - |
| 3 | content_type_id | int | - | - | - | - | - | - | - |
| 4 | codename | varchar(100) | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| auth_permission_content_type_id_codename_01ab375a_uniq | BTREE | Y | - | content_type_id, codename | A, A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| auth_permission_content_type_id_2f476e4b_fk_django_co | content_type_id | django_content_type | id |

### 3.6 auth_user

- 表类型：table
- 来源模型：auth.User
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：4
- 表注释：-
- 创建时间：2026-02-24 05:01:36
- 最近更新时间：2026-03-30 06:30:18

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | int | - | - | Y | - | Y | auto_increment | - |
| 2 | password | varchar(128) | - | - | - | - | - | - | - |
| 3 | last_login | datetime(6) | Y | - | - | - | - | - | - |
| 4 | is_superuser | tinyint(1) | - | - | - | - | - | - | - |
| 5 | username | varchar(150) | - | - | - | Y | - | - | - |
| 6 | first_name | varchar(150) | - | - | - | - | - | - | - |
| 7 | last_name | varchar(150) | - | - | - | - | - | - | - |
| 8 | email | varchar(254) | - | - | - | - | - | - | - |
| 9 | is_staff | tinyint(1) | - | - | - | - | - | - | - |
| 10 | is_active | tinyint(1) | - | - | - | - | - | - | - |
| 11 | date_joined | datetime(6) | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| username | BTREE | Y | - | username | A |

#### 外键信息

无外键信息。

### 3.7 auth_user_groups

- 表类型：table
- 来源模型：-
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：2
- 表注释：-
- 创建时间：2026-02-24 05:01:35

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | user_id | int | - | - | - | - | - | - | - |
| 3 | group_id | int | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| auth_user_groups_group_id_97559544_fk_auth_group_id | BTREE | - | - | group_id | A |
| auth_user_groups_user_id_group_id_94350c0c_uniq | BTREE | Y | - | user_id, group_id | A, A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| auth_user_groups_group_id_97559544_fk_auth_group_id | group_id | auth_group | id |
| auth_user_groups_user_id_6a12ed8b_fk_auth_user_id | user_id | auth_user | id |

### 3.8 auth_user_user_permissions

- 表类型：table
- 来源模型：-
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：0
- 表注释：-
- 创建时间：2026-02-24 05:01:35

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | user_id | int | - | - | - | - | - | - | - |
| 3 | permission_id | int | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm | BTREE | - | - | permission_id | A |
| auth_user_user_permissions_user_id_permission_id_14a6b632_uniq | BTREE | Y | - | user_id, permission_id | A, A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm | permission_id | auth_permission | id |
| auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id | user_id | auth_user | id |

### 3.9 django_admin_log

- 表类型：table
- 来源模型：admin.LogEntry
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：13
- 表注释：-
- 创建时间：2026-02-24 05:01:36

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | int | - | - | Y | - | Y | auto_increment | - |
| 2 | action_time | datetime(6) | - | - | - | - | - | - | - |
| 3 | object_id | longtext | Y | - | - | - | - | - | - |
| 4 | object_repr | varchar(200) | - | - | - | - | - | - | - |
| 5 | action_flag | smallint unsigned | - | - | - | - | - | - | - |
| 6 | change_message | longtext | - | - | - | - | - | - | - |
| 7 | content_type_id | int | Y | - | - | - | - | - | - |
| 8 | user_id | int | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| django_admin_log_content_type_id_c4bce8eb_fk_django_co | BTREE | - | - | content_type_id | A |
| django_admin_log_user_id_c564eba6_fk_auth_user_id | BTREE | - | - | user_id | A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| django_admin_log_content_type_id_c4bce8eb_fk_django_co | content_type_id | django_content_type | id |
| django_admin_log_user_id_c564eba6_fk_auth_user_id | user_id | auth_user | id |

### 3.10 django_content_type

- 表类型：table
- 来源模型：contenttypes.ContentType
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：16
- 表注释：-
- 创建时间：2026-02-24 05:01:36

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | int | - | - | Y | - | Y | auto_increment | - |
| 2 | app_label | varchar(100) | - | - | - | - | - | - | - |
| 3 | model | varchar(100) | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| django_content_type_app_label_model_76bd3d3b_uniq | BTREE | Y | - | app_label, model | A, A |

#### 外键信息

无外键信息。

### 3.11 django_migrations

- 表类型：table
- 来源模型：-
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：30
- 表注释：-
- 创建时间：2026-02-24 05:01:34
- 最近更新时间：2026-03-30 02:22:10

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | app | varchar(255) | - | - | - | - | - | - | - |
| 3 | name | varchar(255) | - | - | - | - | - | - | - |
| 4 | applied | datetime(6) | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |

#### 外键信息

无外键信息。

### 3.12 django_session

- 表类型：table
- 来源模型：sessions.Session
- 分类：系统表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：2
- 表注释：-
- 创建时间：2026-02-24 05:01:37
- 最近更新时间：2026-03-30 06:32:51

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | session_key | varchar(40) | - | - | Y | - | - | - | - |
| 2 | session_data | longtext | - | - | - | - | - | - | - |
| 3 | expire_date | datetime(6) | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | session_key | A |
| django_session_expire_date_a5c62663 | BTREE | - | - | expire_date | A |

#### 外键信息

无外键信息。

### 3.13 feedback_feedback

- 表类型：table
- 来源模型：feedback.Feedback
- 分类：业务表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：11
- 表注释：-
- 创建时间：2026-03-03 06:49:22
- 最近更新时间：2026-03-30 06:35:48

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | scene | varchar(32) | - | - | - | - | - | - | - |
| 3 | task_type | varchar(64) | - | - | - | - | - | - | - |
| 4 | task_id | varchar(64) | - | - | - | - | - | - | - |
| 5 | rating | smallint | - | - | - | - | - | - | - |
| 6 | comment | longtext | - | - | - | - | - | - | - |
| 7 | extra | json | - | - | - | - | - | - | - |
| 8 | created_at | datetime(6) | - | - | - | - | - | - | - |
| 9 | user_id | int | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| feedback_fe_scene_61ca03_idx | BTREE | - | - | scene, created_at | A, A |
| feedback_fe_task_ty_12d04e_idx | BTREE | - | - | task_type, task_id | A, A |
| feedback_fe_user_id_be0124_idx | BTREE | - | - | user_id, created_at | A, A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| feedback_feedback_user_id_f7dd5014_fk_auth_user_id | user_id | auth_user | id |

### 3.14 kb_kbentity

- 表类型：table
- 来源模型：kb.KBEntity
- 分类：业务表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：1
- 表注释：-
- 创建时间：2026-03-25 09:51:51
- 最近更新时间：2026-03-31 03:03:34

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | entity_key | varchar(200) | - | - | - | Y | - | - | - |
| 3 | canonical_key | varchar(200) | - | - | - | - | - | - | - |
| 4 | category | varchar(100) | - | - | - | - | - | - | - |
| 5 | source | varchar(100) | - | - | - | - | - | - | - |
| 6 | langs | json | - | - | - | - | - | - | - |
| 7 | created_at | datetime(6) | - | - | - | - | - | - | - |
| 8 | updated_at | datetime(6) | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| entity_key | BTREE | Y | - | entity_key | A |

#### 外键信息

无外键信息。

### 3.15 kb_rawkbupload

- 表类型：table
- 来源模型：kb.RawKBUpload
- 分类：业务表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：8
- 表注释：-
- 创建时间：2026-03-25 09:51:51
- 最近更新时间：2026-03-30 09:32:58

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | file | varchar(100) | Y | - | - | - | - | - | - |
| 3 | content | longtext | - | - | - | - | - | - | - |
| 4 | file_type | varchar(20) | - | - | - | - | - | - | - |
| 5 | status | varchar(20) | - | - | - | - | - | - | - |
| 6 | created_at | datetime(6) | - | - | - | - | - | - | - |
| 7 | updated_at | datetime(6) | - | - | - | - | - | - | - |
| 8 | uploaded_by_id | int | Y | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| kb_rawkbupload_uploaded_by_id_67d76fff_fk_auth_user_id | BTREE | - | - | uploaded_by_id | A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| kb_rawkbupload_uploaded_by_id_67d76fff_fk_auth_user_id | uploaded_by_id | auth_user | id |

### 3.16 kb_termcard

- 表类型：table
- 来源模型：kb.TermCard
- 分类：业务表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：5
- 表注释：-
- 创建时间：2026-03-25 09:51:52
- 最近更新时间：2026-03-31 03:03:34

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | lang | varchar(8) | - | - | - | - | - | - | - |
| 3 | term | varchar(512) | - | - | - | - | - | - | - |
| 4 | type | varchar(64) | - | - | - | - | - | - | - |
| 5 | explain_text | longtext | - | - | - | - | - | - | - |
| 6 | entity_id | bigint | - | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| kb_termcard_entity_id_ea098519_fk_kb_kbentity_id | BTREE | - | - | entity_id | A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| kb_termcard_entity_id_ea098519_fk_kb_kbentity_id | entity_id | kb_kbentity | id |

### 3.17 qa_qatask

- 表类型：table
- 来源模型：qa.QATask
- 分类：业务表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：98
- 表注释：-
- 创建时间：2026-02-25 07:38:38
- 最近更新时间：2026-03-30 06:32:51

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | question | longtext | - | - | - | - | - | - | - |
| 3 | lang | varchar(16) | - | - | - | - | - | - | - |
| 4 | answer | longtext | - | - | - | - | - | - | - |
| 5 | confidence | double | - | - | - | - | - | - | - |
| 6 | sources_json | json | - | - | - | - | - | - | - |
| 7 | latency_ms | int | - | - | - | - | - | - | - |
| 8 | status | varchar(16) | - | - | - | - | - | - | - |
| 9 | created_at | datetime(6) | - | - | - | - | - | - | - |
| 10 | user_id | int | Y | - | - | - | - | - | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| qa_qatask_user_id_d161d646_fk_auth_user_id | BTREE | - | - | user_id | A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| qa_qatask_user_id_d161d646_fk_auth_user_id | user_id | auth_user | id |

### 3.18 translation_translationtask

- 表类型：table
- 来源模型：translation.TranslationTask
- 分类：业务表
- 存储引擎：InnoDB
- 排序规则：utf8mb4_unicode_ci
- 预估行数：262
- 表注释：-
- 创建时间：2026-03-25 06:13:44
- 最近更新时间：2026-03-31 01:34:39

#### 字段信息

| 序号 | 字段名 | 数据库类型 | 可空 | 默认值 | 主键 | 唯一 | 自增 | 额外属性 | 字段注释 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | id | bigint | - | - | Y | - | Y | auto_increment | - |
| 2 | src_lang | varchar(16) | - | - | - | - | - | - | - |
| 3 | tgt_lang | varchar(16) | - | - | - | - | - | - | - |
| 4 | domain | varchar(32) | - | - | - | - | - | - | - |
| 5 | input_text | longtext | - | - | - | - | - | - | - |
| 6 | output_text | longtext | - | - | - | - | - | - | - |
| 7 | terms_json | json | - | - | - | - | - | - | - |
| 8 | latency_ms | int | - | - | - | - | - | - | - |
| 9 | status | varchar(16) | - | - | - | - | - | - | - |
| 10 | created_at | datetime(6) | - | - | - | - | - | - | - |
| 11 | user_id | int | - | - | - | - | - | - | - |
| 12 | base_translation | longtext | - | _utf8mb4\\'\\' | - | - | - | DEFAULT_GENERATED | - |
| 13 | lora_translation | longtext | - | _utf8mb4\\'\\' | - | - | - | DEFAULT_GENERATED | - |

#### 索引信息

| 索引名 | 类型 | 唯一 | 主键 | 字段列表 | 排序 |
| --- | --- | --- | --- | --- | --- |
| PRIMARY | BTREE | Y | Y | id | A |
| translation_translationtask_user_id_1cf22a12_fk_auth_user_id | BTREE | - | - | user_id | A |

#### 外键信息

| 外键名 | 字段 | 关联表 | 关联字段 |
| --- | --- | --- | --- |
| translation_translationtask_user_id_1cf22a12_fk_auth_user_id | user_id | auth_user | id |
