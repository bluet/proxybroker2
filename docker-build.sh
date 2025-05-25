#!/bin/bash

VERSION=v2.0.0b1
IMAGE_NAME=bluet/proxybroker2

docker build --pull -t ${IMAGE_NAME} .
#docker scan ${IMAGE_NAME}:latest
docker scout quickview ${IMAGE_NAME}:latest
grype ${IMAGE_NAME}:latest | grep -i -E '(High|Critical)'


docker tag ${IMAGE_NAME}:latest ${IMAGE_NAME}:${VERSION}


# Fixes busybox trigger error https://github.com/tonistiigi/xx/issues/36#issuecomment-926876468
#docker run --privileged -it --rm tonistiigi/binfmt --install all

#docker buildx create --use

while true; do
        read -p "Build for multi-platform and push? (Have I Updated VERSION Info? Is the latest VERSION=${VERSION} ?) [y/N]" yn
        case $yn in
                [Yy]* ) docker buildx build --builder cloud-bluet-test -t ${IMAGE_NAME}:latest -t ${IMAGE_NAME}:${VERSION} --platform linux/amd64,linux/arm64/v8 --pull --push .; break;;
                [Nn]* ) exit;;
                * ) echo "";;
        esac
done

while true; do
        read -p "Add new git tag ${VERSION} and push? (Have you git add and git commit already?) [y/N]" yn
        case $yn in
                [Yy]* ) git tag "${VERSION}" -a -m "${VERSION}" && git push && git push --tags; break;;
                [Nn]* ) exit;;
                * ) echo "";;
        esac
done

