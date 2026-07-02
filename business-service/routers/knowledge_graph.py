"""
知识图谱路由
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shared import get_db
from services.knowledge_graph_service import knowledge_graph_service

router = APIRouter(prefix="/knowledge-graph", tags=["知识图谱"])


class GraphGenerateRequest(BaseModel):
    force_rebuild: bool = Field(True, description="是否强制重建图谱")


class GraphQuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="自然语言问题")


class GraphRecommendationRequest(BaseModel):
    defect_type: str = Field(..., min_length=1, description="缺陷类型")
    severity_level: Optional[int] = Field(None, description="严重程度等级")


@router.post("/generate")
async def generate_knowledge_graph(
    request: GraphGenerateRequest,
    db: Session = Depends(get_db),
):
    """生成或重建知识图谱"""
    try:
        result = knowledge_graph_service.generate_graph(
            db,
            force_rebuild=request.force_rebuild,
        )
        return {
            "code": 0,
            "message": "知识图谱生成成功",
            "data": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overview")
async def get_knowledge_graph_overview(db: Session = Depends(get_db)):
    """获取知识图谱概览统计"""
    try:
        return {
            "code": 0,
            "message": "success",
            "data": knowledge_graph_service.get_overview(db),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph")
async def get_knowledge_graph(
    keyword: str = Query("", description="关键词"),
    entity_type: str = Query("", description="实体类型过滤"),
    defect_type: str = Query("", description="缺陷类型过滤"),
    section_name: str = Query("", description="路段过滤"),
    limit: int = Query(80, ge=20, le=150, description="节点数量限制"),
    db: Session = Depends(get_db),
):
    """获取知识图谱节点和关系"""
    try:
        data = knowledge_graph_service.get_graph(
            db,
            keyword=keyword,
            entity_type=entity_type,
            defect_type=defect_type,
            section_name=section_name,
            limit=limit,
        )
        return {
            "code": 0,
            "message": "success",
            "data": data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities")
async def search_knowledge_entities(
    keyword: str = Query("", description="搜索关键词"),
    entity_type: str = Query("", description="实体类型过滤"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    db: Session = Depends(get_db),
):
    """搜索知识图谱实体"""
    try:
        return {
            "code": 0,
            "message": "success",
            "data": knowledge_graph_service.search_entities(
                db,
                keyword=keyword,
                entity_type=entity_type,
                limit=limit,
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/question")
async def ask_knowledge_question(
    request: GraphQuestionRequest,
    db: Session = Depends(get_db),
):
    """自然语言问答"""
    try:
        return {
            "code": 0,
            "message": "success",
            "data": knowledge_graph_service.ask_question(db, request.question),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recommendation")
async def get_knowledge_recommendation(
    request: GraphRecommendationRequest,
    db: Session = Depends(get_db),
):
    """获取缺陷相关的成因、措施和规范推荐"""
    try:
        return {
            "code": 0,
            "message": "success",
            "data": knowledge_graph_service.get_recommendation(
                db,
                defect_type=request.defect_type,
                severity_level=request.severity_level,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

