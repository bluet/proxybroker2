# VERSIONS ---------------------------------------------------------------------
IMG_VER=2.0.0-alpha5
PY_VARIANT=3.8
PY_IMG_VARIANT=slim-buster
POETRY_VARIANT=1.3.1
APP_NAME=proxybroker2
OWNER_NAME=mcgr0g
IMG_NAME=$(OWNER_NAME)/$(APP_NAME)
BUILD_DATE:=$(shell date '+%Y-%m-%d')

BFLAGS=docker buildx build \
		--build-arg IMG_VER=$(IMG_VER) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		--build-arg PY_VARIANT=$(PY_VARIANT) \
		--build-arg PY_IMG_VARIANT=$(PY_IMG_VARIANT) \
		--build-arg POETRY_VARIANT=$(POETRY_VARIANT) \
		--build-arg APP_NAME=$(APP_NAME) \
		--build-arg OWNER_NAME=$(OWNER_NAME) \
		--tag $(IMG_NAME):$(IMG_VER) \
		--tag $(IMG_NAME):latest

BUILD_FAST=$(BFLAGS) .
BUILD_FULL=$(BFLAGS) --progress=plain --no-cache .

# IMAGE -----------------------------------------------------------------------

img-build: kit-install
	$(BUILD_FAST)
	
img-build-full:
	$(BUILD_FULL)

img-get-size-final:
	docker images \
	-f "label=org.opencontainers.image.title=$(APP_NAME)" \
	-f "label=org.opencontainers.image.version=$(IMG_VER)" \
	--format "table {{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.CreatedAt}}\t{{.Size}}" \
	$(IMG_NAME):$(IMG_VER)

img-get-size-layered:
	docker history -H $(IMG_NAME):$(IMG_VER)

img-push:
	docker push $(IMG_NAME) --all-tags
# CONTAINER -------------------------------------------------------------------

run-find:
	docker run --rm --name $(APP_NAME) \
	$(IMG_NAME):$(IMG_VER) \
	--log INFO find --types HTTPS --lvl High --countries US UK DE FR NL --strict -l 10

run-serve:
	docker run --rm --name $(APP_NAME) \
	$(IMG_NAME):$(IMG_VER) \
	--log INFO serve --host 127.0.0.1 --port 8888 --types HTTPS --lvl High --countries UK DE FR NL --min-queue 5

# BuildKit -------------------------------------------------------------------
AFLAGS=--platform linux/amd64,linux/arm64/v8 --push #--progress=plain
BUILD_MULIARCH=$(BFLAGS) $(AFLAGS) .
BUILDER_NAME=kofee_shop

kit-install:
	docker buildx install

kit-context: kit-install
	docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
	docker buildx create  --name $(BUILDER_NAME)--use --bootstrap

multi-arch: kit-context
	$(BUILD_MULIARCH)
	docker buildx rm $(BUILDER_NAME)