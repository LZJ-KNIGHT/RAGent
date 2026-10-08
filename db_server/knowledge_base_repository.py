# ============================================================
# knowledge_base_repository.py —— 知识库表的"数据访问层"（Repository 模式）
# 封装对 KnowledgeBase 表的三种操作：增改（add）、删（del）、查全部（list）
# 上层（kb_routes / chat_routes）只调这三个函数，不直接碰 SQLAlchemy ——
# 将来换数据库/改表结构，只改本文件，上层代码零改动
# ============================================================
from db_server.base import KnowledgeBase
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def add_kb_to_db(session: Session, kb_name: str, kb_info: str):
    """建库登记 / 更新描述。注意是 upsert 语义：
    用 ilike 做【不区分大小写】查询 —— 同名库不会报错，而是更新它的 kb_info"""
    try:
        # 查询是否存在相同名称的知识库
        kb = session.query(KnowledgeBase).filter(KnowledgeBase.kb_name.ilike(kb_name)).first()

        if not kb:
            # 如果不存在，创建新的知识库实例
            kb = KnowledgeBase(kb_name=kb_name, kb_info=kb_info)
            session.add(kb)
            session.commit()
            print(f"KnowledgeBase '{kb_name}' created successfully.")
        else:
            # 如果存在，更新知识库信息
            kb.kb_info = kb_info
            session.commit()
            print(f"KnowledgeBase '{kb_name}' updated successfully.")
    except IntegrityError as e:
        # 违反约束（如唯一键冲突）→ 回滚本次操作，不让异常往上炸
        session.rollback()
        print(f"IntegrityError: {e}")
    except Exception as e:
        session.rollback()
        print(f"An error occurred: {e}")


def del_kb_from_db(session: Session, kb_name: str):
    """删库注销。注意和 add 的不对称：这里用 filter_by 【精确匹配、区分大小写】，
    与 add 的 ilike 规则不一致 —— 两处匹配规则应统一（已知待改进项）"""
    try:
        # 查询是否存在指定名称的知识库
        kb_to_delete = session.query(KnowledgeBase).filter_by(kb_name=kb_name).first()

        if kb_to_delete:
            # 如果存在，删除知识库
            session.delete(kb_to_delete)
            session.commit()
            print(f"KnowledgeBase '{kb_name}' deleted successfully.")
        else:
            print(f"KnowledgeBase '{kb_name}' does not exist.")
    except IntegrityError as e:
        session.rollback()
        print(f"IntegrityError: {e}")
    except Exception as e:
        session.rollback()
        print(f"An error occurred: {e}")


def list_kb_from_db(session: Session):
    """查全部知识库。唯一的消费方是 chat_routes：把结果拼成"库名 - 描述"菜单
    填进提示词的 {knowledgebases}，供模型决定查哪个库"""
    all_kbs = session.query(KnowledgeBase).all()
    # 将结果转换为列表
    kbs_list = [
        {
            # "id": kb.id,
            "kb_name": kb.kb_name,
            "kb_info": kb.kb_info
        }
        for kb in all_kbs
    ]
    return kbs_list

