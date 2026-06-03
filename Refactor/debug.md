# 1. Clear Python cache
find src/cf2 -name "*.pyc" -delete 2>/dev/null

# 2. Run Packaging
make pack p=3d
