-- 高速公路缺陷检测系统数据库初始化脚本（修复版）
-- 数据库: defect_detection
-- 编码: UTF-8

-- 1. 创建数据库
DROP DATABASE IF EXISTS defect_detection;
CREATE DATABASE defect_detection
  WITH
  ENCODING = 'UTF8';

-- 连接到新数据库
\c defect_detection;

-- 2. 创建模型管理表
CREATE TABLE models (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  path VARCHAR(500) NOT NULL,
  version VARCHAR(50) DEFAULT 'v1.0',
  description TEXT,
  model_type VARCHAR(50) DEFAULT 'detection',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 创建图片数据库表
CREATE TABLE image_database (
  id SERIAL PRIMARY KEY,
  filename VARCHAR(255) NOT NULL,
  path VARCHAR(500) NOT NULL UNIQUE,
  url VARCHAR(500),
  folder VARCHAR(255) DEFAULT '/',
  size BIGINT,
  mime_type VARCHAR(50),
  width INT,
  height INT,
  is_folder BOOLEAN DEFAULT FALSE,
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 创建推理任务表
CREATE TABLE inference_tasks (
  id SERIAL PRIMARY KEY,
  task_id VARCHAR(100) UNIQUE NOT NULL,
  model_id INT REFERENCES models(id),
  image_count INT DEFAULT 0,
  status VARCHAR(50) NOT NULL DEFAULT 'pending',
  source_type VARCHAR(50),
  result_path VARCHAR(500),
  error_message TEXT,
  progress FLOAT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  started_at TIMESTAMP,
  completed_at TIMESTAMP
);

-- 5. 创建推理结果表
CREATE TABLE inference_results (
  id SERIAL PRIMARY KEY,
  task_id VARCHAR(100) REFERENCES inference_tasks(task_id) ON DELETE CASCADE,
  original_image VARCHAR(500) NOT NULL,
  result_image VARCHAR(500) NOT NULL,
  detections JSONB,
  confidence FLOAT,
  processing_time FLOAT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. 创建索引
CREATE INDEX idx_image_folder ON image_database(folder);
CREATE INDEX idx_image_uploaded_at ON image_database(uploaded_at);
CREATE INDEX idx_task_status ON inference_tasks(status);
CREATE INDEX idx_task_created_at ON inference_tasks(created_at);
CREATE INDEX idx_result_task_id ON inference_results(task_id);
CREATE INDEX idx_result_created_at ON inference_results(created_at);

-- 7. 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_models_updated_at BEFORE UPDATE ON models
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 8. 插入初始模型数据（使用反斜杠转义）
INSERT INTO models (name, path, version, description, model_type) VALUES
('best.pt', 'G:\\ShuangChuang\\ShuangC\\ultralytics-main\\runs\\detect\\train4_highrpd_v2\\weights\\best.pt', 'v2.0', 'HighRPD Defect Detection Model', 'detection');

-- 完成
SELECT 'Database initialization completed successfully!' as status;
SELECT 'Total tables created: ' || COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' as info;
