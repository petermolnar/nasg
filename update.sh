#!/usr/bin/env bash

if [ -f "/tmp/petermolnar.net.generator.lock" ]; then
	exit 0;
fi;

lastfile="$(find /home/petermolnar.net/source/ -type f -name *.md -printf '%T+ %p\n' | sort | tail -n1 | awk '{print $2}')"; 
lastfilemod=$(stat -c %Y "$lastfile"); 
lastrunfile="/tmp/generator_last_run";  
lastrun=0; 

if [ -f "$lastrunfile" ]; then 
	lastrun=$(stat -c %Y "$lastrunfile"); 
fi; 

if [ "$lastrun" -lt "$lastfilemod" ]; then 
	cd /home/petermolnar.net/src; ../.venv/bin/python3.5 generator.py; 
fi;

exit 0;
