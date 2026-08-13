from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from app.common import keys as ke

router = APIRouter(tags=["页面 (Pages)"])

templates = Jinja2Templates(directory="app/templates")

# 强制禁用 Jinja2 Environment 模板字节码缓存：任何模式（Debug/生产）下都从磁盘重新读模板。
# 这次 JS 目录结构大迁移过渡阶段用，杜绝渲染旧 HTML 字节码返回旧脚本 src。
# 迁移稳定后（所有用户浏览器都已拿到新 HTML）可改回默认 auto_reload=False 以获得性能。
templates.env.cache = None
templates.env.auto_reload = True

# 迁移期版本号 bump：1.0 
APP_VERSION = "1.0"


def _page_response(template: str, request: Request, extra_context: dict | None = None) -> Response:
    """统一页面响应：附带版本号给静态资源查询串 + HTML no-cache（允许 304 但避免强缓存）。"""
    context = {ke.KEY_REQUEST: request, "app_version": APP_VERSION}
    if extra_context:
        context.update(extra_context)
    resp = templates.TemplateResponse(template, context)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@router.get("/", response_class=HTMLResponse, summary="主页面")
async def page_index(request: Request):
    return _page_response("index.html", request)


@router.get("/novel", response_class=HTMLResponse, summary="小说工作台")
async def page_novel(request: Request):
    return _page_response("novel.html", request)


@router.get("/resources", response_class=HTMLResponse, summary="素材资源页")
async def page_resources(request: Request):
    return _page_response("resources.html", request)


@router.get("/config", response_class=HTMLResponse, summary="配置页")
async def page_config(request: Request):
    return _page_response("config.html", request)


@router.get("/rule", response_class=HTMLResponse, summary="规则页")
async def page_rule(request: Request):
    return _page_response("rule.html", request)


@router.get("/message-wall", response_class=HTMLResponse, summary="留言墙")
async def page_message_wall(request: Request):
    return _page_response("message-wall.html", request)
