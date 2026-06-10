#!/bin/bash
case "$1" in
    *Username*) echo "x-access-token" ;;
    *Password*) grep "^GITHUB_PAT=" /mnt/c/Users/angel/WinBet/.env | cut -d= -f2 ;;
    *) echo "x-access-token" ;;
esac
