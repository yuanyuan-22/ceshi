from __future__ import annotations


MANUAL_ENTITIES = [
    {
        "entity_id": "manual_hypertension",
        "canonical_key": "hypertension",
        "category": "disease",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "高血压", "aliases": ["血压高", "高血压病"]},
            "en": {"name": "hypertension", "aliases": ["high blood pressure"]},
            "ja": {"name": "高血圧", "aliases": []},
            "fr": {"name": "hypertension", "aliases": []},
            "de": {"name": "Hypertonie", "aliases": ["Bluthochdruck"]},
        },
        "lang_texts": {
            "zh": {
                "definition": "高血压是以动脉血压持续升高为主要特征的慢性心血管疾病。",
                "notes": "长期控制血压有助于降低脑卒中、冠心病和肾损害风险。",
            }
        },
    },
    {
        "entity_id": "manual_diabetes",
        "canonical_key": "diabetes",
        "category": "disease",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "糖尿病", "aliases": ["糖尿病患者"]},
            "en": {"name": "diabetes", "aliases": ["diabetes mellitus"]},
            "ja": {"name": "糖尿病", "aliases": []},
            "fr": {"name": "diabète", "aliases": []},
            "de": {"name": "Diabetes", "aliases": ["Diabetes mellitus"]},
        },
        "lang_texts": {
            "zh": {
                "definition": "糖尿病是一组以慢性高血糖为特征的代谢性疾病。",
                "notes": "常见管理方式包括饮食控制、运动、血糖监测和药物治疗。",
            }
        },
    },
    {
        "entity_id": "manual_aspirin",
        "canonical_key": "aspirin",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "阿司匹林", "aliases": ["阿司匹林肠溶片"]},
            "en": {"name": "aspirin", "aliases": ["acetylsalicylic acid"]},
            "ja": {"name": "アスピリン", "aliases": []},
            "fr": {"name": "aspirine", "aliases": []},
            "de": {"name": "Aspirin", "aliases": ["Acetylsalicylsäure"]},
        },
        "lang_texts": {
            "zh": {
                "definition": "阿司匹林是常用的解热镇痛和抗血小板药物。",
                "treatment": "常用于发热、轻中度疼痛，以及部分心脑血管疾病的抗血小板治疗。",
                "notes": "应注意胃肠道不适、出血风险以及禁忌证。",
            }
        },
    },
    {
        "entity_id": "manual_ibuprofen",
        "canonical_key": "ibuprofen",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "布洛芬", "aliases": ["布洛芬缓释胶囊"]},
            "en": {"name": "ibuprofen", "aliases": []},
            "ja": {"name": "イブプロフェン", "aliases": []},
            "fr": {"name": "ibuprofène", "aliases": []},
            "de": {"name": "Ibuprofen", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "布洛芬是常用的非甾体抗炎药，可用于退热、止痛和抗炎。",
                "notes": "使用时应注意胃肠道刺激、肾功能风险和合并用药相互作用。",
            }
        },
    },
    {
        "entity_id": "manual_paracetamol",
        "canonical_key": "paracetamol",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "对乙酰氨基酚", "aliases": ["扑热息痛"]},
            "en": {"name": "paracetamol", "aliases": ["acetaminophen"]},
            "ja": {"name": "アセトアミノフェン", "aliases": []},
            "fr": {"name": "paracétamol", "aliases": []},
            "de": {"name": "Paracetamol", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "对乙酰氨基酚是常用退热镇痛药。",
                "notes": "常用于发热和轻中度疼痛，需注意过量使用可能导致肝损伤。",
            }
        },
    },
    {
        "entity_id": "manual_amoxicillin",
        "canonical_key": "amoxicillin",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "阿莫西林", "aliases": ["阿莫西林胶囊"]},
            "en": {"name": "amoxicillin", "aliases": []},
            "ja": {"name": "アモキシシリン", "aliases": []},
            "fr": {"name": "amoxicilline", "aliases": []},
            "de": {"name": "Amoxicillin", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "阿莫西林是常用青霉素类抗生素。",
                "treatment": "常用于细菌感染治疗，如呼吸道、耳鼻喉或泌尿系统感染。",
                "notes": "需注意青霉素过敏史，不适用于病毒性感染。",
            }
        },
    },
    {
        "entity_id": "manual_metformin",
        "canonical_key": "metformin",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "二甲双胍", "aliases": ["盐酸二甲双胍"]},
            "en": {"name": "metformin", "aliases": []},
            "ja": {"name": "メトホルミン", "aliases": []},
            "fr": {"name": "metformine", "aliases": []},
            "de": {"name": "Metformin", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "二甲双胍是 2 型糖尿病常用口服降糖药。",
                "notes": "主要用于改善胰岛素抵抗和降低血糖，需关注胃肠道反应及肾功能。",
            }
        },
    },
    {
        "entity_id": "manual_atorvastatin",
        "canonical_key": "atorvastatin",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "阿托伐他汀", "aliases": ["阿托伐他汀钙片"]},
            "en": {"name": "atorvastatin", "aliases": []},
            "ja": {"name": "アトルバスタチン", "aliases": []},
            "fr": {"name": "atorvastatine", "aliases": []},
            "de": {"name": "Atorvastatin", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "阿托伐他汀是常用他汀类降脂药。",
                "notes": "主要用于降低胆固醇和心血管风险，需注意肝功能及肌肉不良反应。",
            }
        },
    },
    {
        "entity_id": "manual_omeprazole",
        "canonical_key": "omeprazole",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "奥美拉唑", "aliases": ["奥美拉唑肠溶胶囊"]},
            "en": {"name": "omeprazole", "aliases": []},
            "ja": {"name": "オメプラゾール", "aliases": []},
            "fr": {"name": "oméprazole", "aliases": []},
            "de": {"name": "Omeprazol", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "奥美拉唑是常用质子泵抑制剂。",
                "treatment": "常用于胃食管反流、胃溃疡、十二指肠溃疡等酸相关疾病。",
                "notes": "应根据疗程规范使用，长期使用需关注潜在不良反应。",
            }
        },
    },
    {
        "entity_id": "manual_oral_glucose_solution",
        "canonical_key": "oral glucose solution",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "葡萄糖口服液", "aliases": ["口服葡萄糖溶液"]},
            "en": {"name": "oral glucose solution", "aliases": ["glucose oral solution"]},
            "ja": {"name": "ブドウ糖内服液", "aliases": []},
            "fr": {"name": "solution orale de glucose", "aliases": []},
            "de": {"name": "orale Glukoselösung", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "葡萄糖口服液用于补充葡萄糖和能量。",
                "treatment": "可用于轻度低血糖时快速补充糖分，或作为口服营养支持的一部分。",
                "notes": "糖尿病患者及血糖异常人群应在医生指导下使用。",
            }
        },
    },
    {
        "entity_id": "manual_ganmaoling",
        "canonical_key": "ganmaoling",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "感冒灵", "aliases": ["感冒灵颗粒"]},
            "en": {"name": "Ganmaoling", "aliases": ["Ganmaoling granules"]},
            "ja": {"name": "感冒霊", "aliases": []},
            "fr": {"name": "Ganmaoling", "aliases": []},
            "de": {"name": "Ganmaoling", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "感冒灵是常见复方感冒类药品。",
                "treatment": "常用于缓解感冒引起的头痛、发热、鼻塞等症状。",
                "notes": "属于对症用药，应注意成分重复和特殊人群禁忌。",
            }
        },
    },
    {
        "entity_id": "manual_fever",
        "canonical_key": "fever",
        "category": "symptom",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "发热", "aliases": ["发烧"]},
            "en": {"name": "fever", "aliases": []},
            "ja": {"name": "発熱", "aliases": []},
            "fr": {"name": "fièvre", "aliases": []},
            "de": {"name": "Fieber", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "发热是体温高于正常范围的常见症状。",
                "notes": "可见于感染、炎症、免疫反应等多种情况，应结合病因处理。",
            }
        },
    },
    {
        "entity_id": "manual_cough",
        "canonical_key": "cough",
        "category": "symptom",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "咳嗽", "aliases": []},
            "en": {"name": "cough", "aliases": []},
            "ja": {"name": "咳嗽", "aliases": []},
            "fr": {"name": "toux", "aliases": []},
            "de": {"name": "Husten", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "咳嗽是呼吸道常见保护性反射症状。",
                "notes": "常见于感冒、支气管炎、肺炎等疾病，也可见于过敏或刺激因素。",
            }
        },
    },
    {
        "entity_id": "manual_headache",
        "canonical_key": "headache",
        "category": "symptom",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "头痛", "aliases": []},
            "en": {"name": "headache", "aliases": []},
            "ja": {"name": "頭痛", "aliases": []},
            "fr": {"name": "céphalée", "aliases": ["mal de tête"]},
            "de": {"name": "Kopfschmerzen", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "头痛是临床常见症状，可由紧张、感染、偏头痛或其他疾病引起。",
                "notes": "持续或剧烈头痛需要结合病史、神经系统症状进一步评估。",
            }
        },
    },
    {
        "entity_id": "manual_abdominal_pain",
        "canonical_key": "abdominal pain",
        "category": "symptom",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "腹痛", "aliases": ["肚子痛"]},
            "en": {"name": "abdominal pain", "aliases": ["stomach ache"]},
            "ja": {"name": "腹痛", "aliases": []},
            "fr": {"name": "douleur abdominale", "aliases": []},
            "de": {"name": "Bauchschmerzen", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "腹痛是消化系统及腹腔疾病常见症状。",
                "notes": "需结合疼痛部位、性质、持续时间以及伴随症状判断原因。",
            }
        },
    },
    {
        "entity_id": "manual_chest_pain",
        "canonical_key": "chest pain",
        "category": "symptom",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "胸痛", "aliases": []},
            "en": {"name": "chest pain", "aliases": []},
            "ja": {"name": "胸痛", "aliases": []},
            "fr": {"name": "douleur thoracique", "aliases": []},
            "de": {"name": "Brustschmerzen", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "胸痛可与心血管、呼吸系统或胸壁疾病相关。",
                "notes": "突发胸痛应警惕心肌梗死、肺栓塞等严重情况。",
            }
        },
    },
    {
        "entity_id": "manual_pneumonia",
        "canonical_key": "pneumonia",
        "category": "disease",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "肺炎", "aliases": []},
            "en": {"name": "pneumonia", "aliases": []},
            "ja": {"name": "肺炎", "aliases": []},
            "fr": {"name": "pneumonie", "aliases": []},
            "de": {"name": "Lungenentzündung", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "肺炎是肺实质感染性疾病，可由细菌、病毒等病原体引起。",
                "notes": "常见表现包括发热、咳嗽、咳痰、胸痛或呼吸困难。",
            }
        },
    },
    {
        "entity_id": "manual_bronchitis",
        "canonical_key": "bronchitis",
        "category": "disease",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "支气管炎", "aliases": []},
            "en": {"name": "bronchitis", "aliases": []},
            "ja": {"name": "気管支炎", "aliases": []},
            "fr": {"name": "bronchite", "aliases": []},
            "de": {"name": "Bronchitis", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "支气管炎是支气管黏膜炎症性疾病。",
                "notes": "常见症状包括咳嗽、咳痰、气促，急性和慢性病因有所不同。",
            }
        },
    },
    {
        "entity_id": "manual_gastritis",
        "canonical_key": "gastritis",
        "category": "disease",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "胃炎", "aliases": []},
            "en": {"name": "gastritis", "aliases": []},
            "ja": {"name": "胃炎", "aliases": []},
            "fr": {"name": "gastrite", "aliases": []},
            "de": {"name": "Gastritis", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "胃炎是胃黏膜炎症性病变。",
                "notes": "常见表现为上腹不适、反酸、恶心，需结合诱因与检查判断。",
            }
        },
    },
    {
        "entity_id": "manual_blood_test",
        "canonical_key": "blood routine test",
        "category": "examination",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "血常规", "aliases": ["血常规检查"]},
            "en": {"name": "blood routine test", "aliases": ["complete blood count", "CBC"]},
            "ja": {"name": "血液一般検査", "aliases": []},
            "fr": {"name": "numération formule sanguine", "aliases": ["NFS"]},
            "de": {"name": "Blutbild", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "血常规是常见基础实验室检查，可评估白细胞、红细胞、血红蛋白和血小板情况。",
                "notes": "常用于感染、贫血、出血倾向等初步评估。",
            }
        },
    },
    {
        "entity_id": "manual_ct",
        "canonical_key": "ct",
        "category": "examination",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "CT", "aliases": ["CT检查", "计算机断层扫描"]},
            "en": {"name": "CT", "aliases": ["computed tomography"]},
            "ja": {"name": "CT", "aliases": ["コンピュータ断層撮影"]},
            "fr": {"name": "scanner", "aliases": ["tomodensitométrie", "CT"]},
            "de": {"name": "CT", "aliases": ["Computertomographie"]},
        },
        "lang_texts": {
            "zh": {
                "definition": "CT 是一种常见影像学检查方法，可快速观察体内结构。",
                "notes": "常用于头部、胸部、腹部等部位病变的初步影像评估。",
            }
        },
    },
    {
        "entity_id": "manual_mri",
        "canonical_key": "mri",
        "category": "examination",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "MRI", "aliases": ["磁共振", "核磁共振"]},
            "en": {"name": "MRI", "aliases": ["magnetic resonance imaging"]},
            "ja": {"name": "MRI", "aliases": ["磁気共鳴画像"]},
            "fr": {"name": "IRM", "aliases": ["imagerie par résonance magnétique"]},
            "de": {"name": "MRT", "aliases": ["Magnetresonanztomographie", "MRI"]},
        },
        "lang_texts": {
            "zh": {
                "definition": "MRI 是常用磁共振影像检查，可提供较高软组织分辨率。",
                "notes": "常用于神经系统、关节、脊柱和软组织病变评估。",
            }
        },
    },
    {
        "entity_id": "manual_ecg",
        "canonical_key": "electrocardiogram",
        "category": "examination",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "心电图", "aliases": ["心电图检查", "ECG"]},
            "en": {"name": "electrocardiogram", "aliases": ["ECG", "EKG"]},
            "ja": {"name": "心電図", "aliases": []},
            "fr": {"name": "électrocardiogramme", "aliases": ["ECG"]},
            "de": {"name": "Elektrokardiogramm", "aliases": ["EKG"]},
        },
        "lang_texts": {
            "zh": {
                "definition": "心电图用于记录心脏电活动，是基础心血管检查之一。",
                "notes": "常用于心律失常、心肌缺血、心肌梗死等初步筛查。",
            }
        },
    },
    {
        "entity_id": "manual_cefuroxime",
        "canonical_key": "cefuroxime",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "头孢呋辛", "aliases": ["头孢"]},
            "en": {"name": "cefuroxime", "aliases": []},
            "ja": {"name": "セフロキシム", "aliases": []},
            "fr": {"name": "céfuroxime", "aliases": []},
            "de": {"name": "Cefuroxim", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "头孢呋辛是常用头孢菌素类抗生素。",
                "treatment": "可用于部分细菌感染治疗，如呼吸道、耳鼻喉和泌尿系统感染。",
                "notes": "需注意抗生素过敏史及规范用药。",
            }
        },
    },
    {
        "entity_id": "manual_azithromycin",
        "canonical_key": "azithromycin",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "阿奇霉素", "aliases": []},
            "en": {"name": "azithromycin", "aliases": []},
            "ja": {"name": "アジスロマイシン", "aliases": []},
            "fr": {"name": "azithromycine", "aliases": []},
            "de": {"name": "Azithromycin", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "阿奇霉素是常用大环内酯类抗生素。",
                "treatment": "常用于某些呼吸道感染、皮肤软组织感染等。",
                "notes": "需按疗程规范使用，并注意胃肠反应及药物相互作用。",
            }
        },
    },
    {
        "entity_id": "manual_vitamin_c",
        "canonical_key": "vitamin c",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "维生素C", "aliases": ["维C"]},
            "en": {"name": "vitamin C", "aliases": ["ascorbic acid"]},
            "ja": {"name": "ビタミンC", "aliases": []},
            "fr": {"name": "vitamine C", "aliases": []},
            "de": {"name": "Vitamin C", "aliases": []},
        },
        "lang_texts": {
            "zh": {
                "definition": "维生素C是常见维生素补充剂。",
                "notes": "常用于维生素补充，部分场景用于辅助营养支持。",
            }
        },
    },
    {
        "entity_id": "manual_saline",
        "canonical_key": "sodium chloride injection",
        "category": "drug",
        "source": "manual",
        "source_type": "builtin",
        "lang_terms": {
            "zh": {"name": "氯化钠注射液", "aliases": ["生理盐水"]},
            "en": {"name": "sodium chloride injection", "aliases": ["normal saline"]},
            "ja": {"name": "塩化ナトリウム注射液", "aliases": ["生理食塩水"]},
            "fr": {"name": "solution injectable de chlorure de sodium", "aliases": ["sérum physiologique"]},
            "de": {"name": "Natriumchlorid-Injektion", "aliases": ["physiologische Kochsalzlösung"]},
        },
        "lang_texts": {
            "zh": {
                "definition": "氯化钠注射液是常见基础输液和稀释液。",
                "notes": "常用于补液、药物配制或冲洗等场景，具体使用应遵医嘱。",
            }
        },
    },
]
