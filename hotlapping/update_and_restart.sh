#!/bin/bash

cd ~

steamcmd +force_install_dir ~/server +login anonymous +app_update 1815810 validate +quit

./restart_server.sh
