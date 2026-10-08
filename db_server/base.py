# ============================================================
# db_server/base.py —— SQLite 元数据库的"地基"
# 存什么：知识库登记信息（库名、描述），不存文档内容
# 用什么：SQLAlchemy ORM —— 用 Python 类操作表，不用手写 SQL
# 谁在用：kb_routes（建库登记/删库注销）、chat_routes（查库拼菜单）
# ============================================================
import os

from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from configs.setting import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_DATABASE

# 确保数据库目录存在
if not os.path.exists(SQLALCHEMY_DATABASE):
    os.makedirs(SQLALCHEMY_DATABASE)

# 创建数据库引擎，这里使用的是 SQLite
# URI 形如 sqlite:///db_server/data/info.db；echo=True 会打印每条 SQL 便于学习调试。
# 换 MySQL 只需改连接串（如 mysql+pymysql://...），ORM 代码不用动 —— 这就是 ORM 的价值
engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=True)

# 创建基类，所有模型都将继承自这个基类
Base = declarative_base()


# 定义 KnowledgeBase 模型：一个类 = 一张表，一个属性 = 一列
class KnowledgeBase(Base):
    __tablename__ = 'knowledge_bases'  # 表名

    id = Column(Integer, primary_key=True, autoincrement=True, comment="知识库ID")  # 主键
    kb_name = Column(String(50), comment="知识库名称")  # 知识库名称
    kb_info = Column(String(200), comment="知识库简介(用于Agent)")  # 知识库简介

    def __repr__(self):
        return f"<KnowledgeBase(id='{self.id}', kb_name='{self.kb_name}', kb_info='{self.kb_info}')>"
#
#
# # 创建所有表
# Base.metadata.create_all(engine)

# 创建会话：所有数据库读写都通过这个 session 对象进行。
# 注意这是模块级全局单例 —— 整个应用共用一个会话，demo 够用；
# 多用户生产环境应改成请求级会话（FastAPI 依赖注入 yield session），
# 避免并发请求互相干扰。kb_routes/chat_routes 直接 import 这个 session 用
Session = sessionmaker(bind=engine)
session = Session()