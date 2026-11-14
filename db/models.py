from db.database import get_conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        nickname TEXT,
        persona TEXT DEFAULT '流萤',
        emotion_score REAL DEFAULT 0,
        intimacy INTEGER DEFAULT 0,
        relationship_stage TEXT DEFAULT 'stranger',
        confessed_at TIMESTAMP,
        last_active_at TIMESTAMP,
        balance REAL DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        last_extract_at TIMESTAMP,
        is_sleeping INTEGER DEFAULT 0,
        reply_style TEXT DEFAULT 'normal',
        quiet_start TEXT DEFAULT '',
        quiet_end TEXT DEFAULT '',
        is_minor INTEGER DEFAULT 0,
        quota_week TEXT DEFAULT '',
        quota_used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        total_tokens INTEGER DEFAULT 0,
        message_count INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        user_id TEXT,
        persona TEXT,
        role TEXT,
        content TEXT,
        tokens INTEGER DEFAULT 0,
        extracted INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_msg_user_persona_time
    ON messages(user_id, persona, created_at DESC)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        persona TEXT,
        key TEXT,
        value TEXT,
        priority INTEGER DEFAULT 1,
        pinned INTEGER DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, persona, key)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS invite_codes (
        code TEXT PRIMARY KEY,
        max_uses INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 纪念（里程碑）：只记录已经发生的，不做进度、不发奖励
    cur.execute("""
    CREATE TABLE IF NOT EXISTS milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        persona TEXT,
        key TEXT,
        title TEXT,
        unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, persona, key)
    )
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_milestone_user
    ON milestones(user_id, persona, unlocked_at)
    """)

    # ---- 角色独立状态 ----
    # 好感 / 阶段 / 表白 / 情绪，按 (user_id, persona) 隔离。
    # 以前只有 migrate_split_intimacy.py 建过这张表 —— 删库重建时会直接崩，
    # 所以挪进初始化，保证任何空库都能跑起来。
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_characters (
        user_id TEXT,
        persona TEXT,
        intimacy INTEGER DEFAULT 0,
        relationship_stage TEXT DEFAULT 'stranger',
        confessed_at TIMESTAMP,
        emotion_score REAL DEFAULT 0,
        trust REAL DEFAULT 20,
        energy REAL DEFAULT 1.0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, persona)
    )
    """)

    # 旧库补列：trust（信任）/ energy（精力）
    # 语气 = 好感 + 信任 + 情绪 + 精力 共同决定，见 core/tone.py
    for stmt in (
        "ALTER TABLE user_characters ADD COLUMN trust REAL DEFAULT 20",
        "ALTER TABLE user_characters ADD COLUMN energy REAL DEFAULT 1.0",
    ):
        try:
            cur.execute(stmt)
        except Exception:
            pass

    # ---- 权限列 ----
    # 旧库没有这三列，用 ALTER 补；已经有了就跳过（SQLite 不支持 ADD COLUMN IF NOT EXISTS）
    #   role        四种人：user / vip / admin / banned
    #   daily_limit 个人日额度覆盖（NULL = 用角色默认）
    #   note        备注：谁的朋友、测什么，方便后台认人
    for stmt in (
        "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'",
        "ALTER TABLE users ADD COLUMN daily_limit REAL DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN note TEXT DEFAULT NULL",
        # 回复长短偏好：short / normal / long
        "ALTER TABLE users ADD COLUMN reply_style TEXT DEFAULT 'normal'",
        # 免打扰时段（HH:MM，两项都空 = 不开启）
        "ALTER TABLE users ADD COLUMN quiet_start TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN quiet_end TEXT DEFAULT ''",
        # 2026-11-13：她说话的样子（/voice 页面）。整份设置存成一段 JSON。
        "ALTER TABLE users ADD COLUMN voice_cfg TEXT DEFAULT ''",
        # 未成年人：1 = 走周配额、不谈恋爱线、不扣余额
        "ALTER TABLE users ADD COLUMN is_minor INTEGER DEFAULT 0",
        # 周配额：quota_week = '2026-W43'，跨周自动重置 quota_used
        "ALTER TABLE users ADD COLUMN quota_week TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN quota_used INTEGER DEFAULT 0",
    ):
        try:
            cur.execute(stmt)
        except Exception:
            pass

    # ---- 确信度 ----
    # 不是所有角色都两条轴。只有 config.CERTAINTY_CHARACTERS 里的角色才用。
    # 含义："她对'他是不是那个人'的判断"，跟好感度完全独立。
    for stmt in (
        "ALTER TABLE user_characters ADD COLUMN certainty REAL DEFAULT 0",
    ):
        try:
            cur.execute(stmt)
        except Exception:
            pass

    # ---- 记忆锁定 ----
    # pinned=1 的记忆永不参与裁剪，注入时排最前。
    # 对应功能："记住这个" —— 让用户自己决定什么不能忘。
    for stmt in (
        "ALTER TABLE memories ADD COLUMN pinned INTEGER DEFAULT 0",
        # 长期任务说到第几个阶段了（1=说过20，2=说过50，3=都说过）
        "ALTER TABLE quests ADD COLUMN notified INTEGER DEFAULT 0",
    ):
        try:
            cur.execute(stmt)
        except Exception:
            pass


    # ---- 用户私有角色（自定义智能体）----
    # key 用 custom:<id>；对话和记忆仍走已有的 messages / memories 表，
    # 只是 persona 字段存 custom:<id>。
    cur.execute("""
    CREATE TABLE IF NOT EXISTS custom_personas (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      TEXT NOT NULL,
        name         TEXT,
        call_me      TEXT,
        prompt       TEXT,
        opening      TEXT,
        catchphrases TEXT,
        tone_json    TEXT,
        knows        INTEGER DEFAULT 0,
        stage        TEXT DEFAULT 'A',
        target       TEXT,
        ended_at     TIMESTAMP,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_custom_user ON custom_personas(user_id)"
    )


    # ---- 自定义背景（老友专属）----
    # 每人每个角色最多一张，重传覆盖。status 用于人工审核。
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_bg (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT NOT NULL,
        persona    TEXT NOT NULL,
        file       TEXT,
        status     TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, persona)
    )
    """)


    # ---- 事件（让四维由"发生了什么"驱动）----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL,
        persona         TEXT NOT NULL,
        type            TEXT NOT NULL,
        summary         TEXT,
        intensity       INTEGER DEFAULT 1,
        affection_delta REAL DEFAULT 0,
        trust_delta     REAL DEFAULT 0,
        emotion_delta   REAL DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, persona, created_at)")

    # ---- 承诺（说过要做的事，到期没做算放鸽子）----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS promises (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT NOT NULL,
        persona     TEXT NOT NULL,
        what        TEXT NOT NULL,
        due_at      TIMESTAMP NOT NULL,
        status      TEXT DEFAULT 'open',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_promises_user ON promises(user_id, persona, status)")

    # ---- 长期任务（累积到阈值，改角色机制参数）----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS quests (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT NOT NULL,
        persona    TEXT NOT NULL,
        quest      TEXT NOT NULL,
        points     INTEGER DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, persona, quest)
    )
    """)


    # ---- 生成的剧情（一次生成 = 一份 JSON）----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stories (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        status      TEXT DEFAULT 'pending',
        city        TEXT,
        origin      TEXT,
        days        INTEGER,
        title       TEXT,
        file        TEXT,
        tokens      INTEGER DEFAULT 0,
        cost_yuan   REAL DEFAULT 0,
        charged     REAL DEFAULT 0,
        error       TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stories_user ON stories(user_id, created_at)")

    # ---- 日摘要：跨天的桥 ----
    # 每天第一次说话时，把昨天的对话压成一段日记，第二天注入。
    # 没有这个，跨天就只剩 key-value 标签，说不出那天你怎么说的。
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_summaries (
        user_id    TEXT NOT NULL,
        persona    TEXT NOT NULL,
        day        TEXT NOT NULL,
        summary    TEXT NOT NULL,
        msg_count  INTEGER DEFAULT 0,
        created_at TEXT,
        PRIMARY KEY (user_id, persona, day)
    )
    """)

    # ---- 每日好感上限（存库，否则重启就重置一次）----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_gain (
        user_id TEXT NOT NULL,
        day     TEXT NOT NULL,
        amount  REAL DEFAULT 0,
        PRIMARY KEY (user_id, day)
    )
    """)

    conn.commit()
    conn.close()