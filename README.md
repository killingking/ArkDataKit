https://prts.wiki/w/术语释义

pip install playwright
playwright install

# 先更新源，再安装所有缺失依赖（含 GTK3/XCursor 等）

sudo apt-get update && sudo apt-get install -y \
libx11-xcb1 \
libxcursor1 \
libgtk-3-0 \
libpangocairo-1.0-0 \
libcairo-gobject2 \
libgdk-pixbuf2.0-0 \

# 补全之前 Playwright 要求的基础依赖（避免重复缺失）

libdbus-1-3 \
libatk1.0-0 \
libatk-bridge2.0-0 \
libcups2 \
libdrm2 \
libxkbcommon0 \
libxcomposite1 \
libxdamage1 \
libxfixes3 \
libxrandr2 \
libgbm1 \
libpango-1.0-0 \
libcairo2 \
libasound2 \
libatspi2.0-0
