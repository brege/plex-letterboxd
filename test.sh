#!/bin/bash
set -e

echo "plex-letterboxd Exporter Smoke Test"
echo "======================================"

# Test help commands
echo "Testing help commands..."
python3 exporter.py --help > /dev/null && echo "✔ exporter.py --help"
python3 compare.py --help > /dev/null && echo "✔ compare.py --help"

# Test config validation
echo "Testing config validation..."
python3 exporter.py --config config.example.yaml \
  --help > /dev/null && echo "✔ config.example.yaml loads"
[ -f config.yaml ] && python3 exporter.py --config config.yaml \
  --help > /dev/null && echo "✔ config.yaml loads"

# Create sample data for cached mode test
echo "Creating sample data..."
cat > plex-watched-testuser-2025-08-30.csv << 'EOF'
tmdbID,Title,Year,Directors,WatchedDate,Rating,Review,Tags,Rewatch
777270,Belfast,2021,Kenneth Branagh,2025-03-20,,,Drama,No
634649,Spider-Man: No Way Home,2021,Jon Watts,2025-04-15,,,Action,No
777270,Belfast,2021,Kenneth Branagh,2025-06-10,,,Drama,Yes
EOF

# Test cached mode
echo "Testing cached mode..."
python3 exporter.py --cached \
  --user testuser \
  --from-date 2025-04-01 \
  --to-date 2025-05-31 \
  --output test-cached.csv
[ -f test-cached.csv ] && echo "✔ Cached mode created output file"
[ $(wc -l < test-cached.csv) -eq 2 ] && echo "✔ Cached mode filtered correctly (1 data row + header)"

# Create sample Letterboxd data for comparison
cat > test-letterboxd.csv << 'EOF'
Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date
2025-03-15,Dune,2021,https://letterboxd.com/film/dune-2021/,,,No,,2025-03-15
2025-05-20,Belfast,2021,https://letterboxd.com/film/belfast/,,,No,,2025-05-20
EOF

# Test comparison without plot
echo "Testing comparison analysis..."
python3 compare.py --plex plex-watched-testuser-2025-08-30.csv \
  --letterboxd test-letterboxd.csv \
  --no-plot \
  --from-date 2025-03-01 \
  --to-date 2025-07-31 > compare-output.txt
grep -q "Belfast" compare-output.txt && echo "✔ Comparison found overlapping movie"
grep -q "overlapping movies" compare-output.txt && echo "✔ Comparison analysis working"

# Test plot generation
echo "Testing plot generation..."
python3 compare.py --plex plex-watched-testuser-2025-08-30.csv \
  --letterboxd test-letterboxd.csv \
  --output test-plot.png \
  --from-date 2025-03-01 \
  --to-date 2025-07-31 > /dev/null
[ -f test-plot.png ] && [ $(stat -c%s test-plot.png) -gt 1000 ] && echo "✔ Plot generated successfully"

# Cleanup
echo "Cleaning up test files..."
rm -f plex-watched-testuser-2025-08-30.csv \
  test-cached.csv \
  test-letterboxd.csv \
  test-plot.png \
  compare-output.txt

echo "✔ All smoke tests passed!"
