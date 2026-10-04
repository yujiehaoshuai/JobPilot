"""集中定义固定选项，让模型、筛选规则和数据库使用相同的名称。"""

from enum import StrEnum


class EmploymentType(StrEnum):
    """岗位类型或候选人的求职类型。

    ANY 放在岗位里表示未注明类型；放在候选人资料里表示不限类型。
    """

    ANY = "any"  # 未注明或不限。
    INTERN = "internship"  # 实习。
    FULL_TIME = "full_time"  # 全职。


class SkillLevel(StrEnum):
    """记录候选人自己填写的技能经历，不替候选人推测熟练程度。"""

    LEARNING = "learning"  # 正在学习。
    PROJECT_EXPERIENCE = "project_experience"  # 在项目中实际使用过。
    PROFESSIONAL = "professional"  # 在工作中实际使用过。


class ApplicationStatus(StrEnum):
    """申请进度的固定状态；允许怎样变更由存储层单独控制。

    当前只保存本地记录。写入“已沟通”不代表程序真的发送了消息。
    """

    NEW = "NEW"  # 新建跟踪记录。
    ANALYZED = "ANALYZED"  # 已完成岗位分析。
    SHORTLISTED = "SHORTLISTED"  # 已加入候选岗位名单。
    IGNORED = "IGNORED"  # 暂不考虑。
    CONTACT_READY = "CONTACT_READY"  # 已准备好沟通内容。
    CONTACTED = "CONTACTED"  # 已进行沟通。
    REPLIED = "REPLIED"  # 已收到回复。
    INTERVIEW = "INTERVIEW"  # 已进入面试阶段。
    REJECTED = "REJECTED"  # 申请被拒绝。
    OFFER = "OFFER"  # 已收到录用通知。
    ARCHIVED = "ARCHIVED"  # 已归档，不再变更进度。
