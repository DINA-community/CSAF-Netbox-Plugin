#!/bin/bash
#
# Runs unit tests in a docker compose setup

set -e

doco="docker compose --file $(dirname "$0")/docker-compose.test.yml"

test_cleanup() {
  echo "💣 Cleaning Up"
  $doco down --volumes
}

echo "🐳🐳🐳 Start testing"

# Make sure the cleanup is executed
trap test_cleanup EXIT

echo "⏱ Running CSAF Unit Tests"
$doco run --rm netbox

echo "🐳🐳🐳 Done testing"
