#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Подготовка к отправке в Git ===${NC}"

# Проверяем, инициализирован ли Git в этой папке
if [ ! -d ".git" ]; then
    echo -e "${RED}Ошибка: В этой папке нет Git-репозитория!${NC}"
    echo "Выполните: git init"
    echo "И настройте удаленный репозиторий: git remote add origin <URL>"
    exit 1
fi

# Запрашиваем сообщение коммита
echo -n "Введите сообщение коммита (или нажмите Enter для авто-сообщения): "
read commit_msg

# Если сообщение пустое, генерируем автоматическое
if [ -z "$commit_msg" ]; then
    commit_msg="Auto-commit: $(date '+%Y-%m-%d %H:%M:%S')"
fi

echo -e "${YELLOW}Добавление файлов...${NC}"
git add .

# Проверяем, есть ли что коммитить
if git diff-index --quiet HEAD --; then
    echo -e "${YELLOW}Нет изменений для коммита.${NC}"
else
    echo -e "${YELLOW}Создание коммита: '$commit_msg'${NC}"
    git commit -m "$commit_msg"
fi

echo -e "${YELLOW}Отправка на удаленный сервер (git push)...${NC}"
git push

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Успешно отправлено в Git!${NC}"
else
    echo -e "${RED}❌ Ошибка при отправке. Проверьте подключение к интернету или права доступа.${NC}"
fi
