#!/bin/bash

# until new server setup the files were pushed to whiplash ftp server
# code is kept just in case we want to reactivate

CURRENT_DATE=$(date +"%Y%m")

for file in ${CURRENT_DATE}*; do
    if [ -f "$file" ] && [ $(find "$file" -mmin -60) ]; then
        echo "Uploading $file..."
        curl -v -T "$file" --ftp-create-dirs -u username:password ftp://ftp.infinityfree.com/htdocs/tsu_stats/"$file"
    else
        echo "$file is either not a regular file or not modified within the last hour, skipping..."
    fi
done
