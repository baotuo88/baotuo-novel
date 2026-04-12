-- 迁移脚本：新增 LLM 调用观测日志表
-- 用途：记录模型、时延、请求规模、估算 token/成本及错误信息

CREATE TABLE IF NOT EXISTS llm_call_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    project_id VARCHAR(64) NULL,
    request_type VARCHAR(32) NOT NULL DEFAULT 'chat',
    provider VARCHAR(32) NOT NULL DEFAULT 'openai-compatible',
    model VARCHAR(128) NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'success',
    latency_ms INT NULL,
    input_chars INT NOT NULL DEFAULT 0,
    output_chars INT NOT NULL DEFAULT 0,
    estimated_input_tokens INT NOT NULL DEFAULT 0,
    estimated_output_tokens INT NOT NULL DEFAULT 0,
    estimated_cost_usd DECIMAL(16,8) NULL,
    finish_reason VARCHAR(32) NULL,
    error_type VARCHAR(64) NULL,
    error_message TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_llm_call_logs_created_at (created_at),
    INDEX idx_llm_call_logs_status (status),
    INDEX idx_llm_call_logs_user_id (user_id),
    INDEX idx_llm_call_logs_project_id (project_id),
    CONSTRAINT fk_llm_call_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);
