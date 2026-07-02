-- 高速公路缺陷检测系统数据库初始化脚本
-- 数据库: defect_detection

-- 1. 创建数据库
DROP DATABASE IF EXISTS defect_detection;
CREATE DATABASE defect_detection
  WITH
  ENCODING = 'UTF8'
  LC_COLLATE = 'Chinese (Simplified)_China.936'
  LC_CTYPE = 'Chinese (Simplified)_China.936';

-- 连接到新数据库
\c defect_detection;

-- 2. 创建模型管理表
CREATE TABLE models (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,           -- 模型文件名
  path VARCHAR(500) NOT NULL,                  -- 模型文件路径
  version VARCHAR(50) DEFAULT 'v1.0',          -- 版本号
  description TEXT,                            -- 描述
  model_type VARCHAR(50) DEFAULT 'detection',  -- 模型类型: detection/tracking
  is_active BOOLEAN DEFAULT TRUE,              -- 是否激活
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. 创建图片数据库表
CREATE TABLE image_database (
  id SERIAL PRIMARY KEY,
  filename VARCHAR(255) NOT NULL,              -- 文件名
  path VARCHAR(500) NOT NULL UNIQUE,           -- 文件路径
  url VARCHAR(500),                            -- 访问 URL
  folder VARCHAR(255) DEFAULT '/',             -- 所属文件夹
  size BIGINT,                                 -- 文件大小(字节)
  mime_type VARCHAR(50),                       -- MIME 类型
  width INT,                                   -- 图片宽度
  height INT,                                  -- 图片高度
  is_folder BOOLEAN DEFAULT FALSE,             -- 是否是文件夹
  uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. 创建推理任务表
CREATE TABLE inference_tasks (
  id SERIAL PRIMARY KEY,
  task_id VARCHAR(100) UNIQUE NOT NULL,        -- 任务唯一标识
  model_id INT REFERENCES models(id),          -- 使用的模型
  image_count INT DEFAULT 0,                   -- 图片数量
  status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending/processing/completed/failed
  source_type VARCHAR(50),                     -- 来源: upload/database/video
  result_path VARCHAR(500),                    -- 结果压缩包路径
  error_message TEXT,                          -- 错误信息
  progress FLOAT DEFAULT 0,                    -- 进度 0-100
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  started_at TIMESTAMP,
  completed_at TIMESTAMP
);

-- 5. 创建推理结果表
CREATE TABLE inference_results (
  id SERIAL PRIMARY KEY,
  task_id VARCHAR(100) REFERENCES inference_tasks(task_id) ON DELETE CASCADE,
  original_image VARCHAR(500) NOT NULL,        -- 原始图片路径
  result_image VARCHAR(500) NOT NULL,          -- 结果图片路径
  detections JSONB,                            -- 检测结果 JSON
  confidence FLOAT,                            -- 平均置信度
  processing_time FLOAT,                       -- 处理耗时(秒)
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. 创建索引
CREATE INDEX idx_image_folder ON image_database(folder);
CREATE INDEX idx_image_uploaded_at ON image_database(uploaded_at);
CREATE INDEX idx_task_status ON inference_tasks(status);
CREATE INDEX idx_task_created_at ON inference_tasks(created_at);
CREATE INDEX idx_result_task_id ON inference_results(task_id);
CREATE INDEX idx_result_created_at ON inference_results(created_at);

-- 7. 插入初始模型数据
INSERT INTO models (name, path, version, description, model_type) VALUES
('best.pt', 'G:\ShuangChuang\ShuangC\ultralytics-main\runs\detect\train4_highrpd_v2\weights\best.pt', 'v2.0', '高速公路缺陷检测模型 - 最佳权重', 'detection');

-- 8. 插入测试图片数据（从数据集导入）
-- 注意: 实际图片数据请使用 import_dataset.py 导入
-- INSERT INTO image_database (filename, path, folder, size, mime_type) VALUES
-- ('example.jpg', 'G:\ShuangChuang\ShuangC\backend\uploads\images\example.jpg', '/测试', 1024000, 'image/jpeg');

-- 9. 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_models_updated_at BEFORE UPDATE ON models
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 完成
SELECT 'Database initialization completed successfully!' as status;
