#!/bin/sh
# Builds the static site for Netlify: the page, its assets, and a proxy from /api to the Cloud Run backend.
set -e
API="${STAIRCASE_API:-https://staircase-rqmoel4gfa-uw.a.run.app}"
rm -rf site && mkdir -p site/static
cp static/index.html site/index.html
cp static/style.css static/app.js static/favicon.svg static/favicon-32.png static/apple-touch-icon.png site/static/
printf '/api/*  %s/api/:splat  200\n' "$API" > site/_redirects
