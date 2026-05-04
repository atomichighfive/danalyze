VERSION ?= $(shell python -c "from danalyze import __version__; print(__version__)")

.PHONY: install build release

install:
	uv tool install --editable .

build:
	uv build

release: build
	git tag v$(VERSION)
	git push origin v$(VERSION)
	gh release create v$(VERSION) dist/danalyze-$(VERSION)-*.whl \
		--title "danalyze v$(VERSION)" --notes ""
