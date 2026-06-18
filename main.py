import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from api.user      import user_router
from api.auth      import auth_router
from api.admin     import admin_router
from api.upload    import upload_router
from api.printfile import print_router
from api.topdf     import topdf_router
from core.cleaner   import start_cleaner
from core.config    import get_app_dir

# 静态文件目录（开发=项目根/static，打包=exe旁边/static）
_STATIC_DIR = os.path.join(get_app_dir(), "static")

# 启动定时文件清理任务（每天凌晨 4 点）
start_cleaner()

app = FastAPI()

@app.get("/")
def root():
    """根路径重定向到登录页"""
    return RedirectResponse(url="/static/index.html")

app.include_router(user_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(upload_router)
app.include_router(print_router)
app.include_router(topdf_router)

app.mount("/static", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
