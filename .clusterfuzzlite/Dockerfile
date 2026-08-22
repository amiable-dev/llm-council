FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:6b2b3a7e4a2da50de47f94925cffbe34747e1aae4f33d7f07ba6c681dd648b23

COPY . $SRC/llm-council
COPY .clusterfuzzlite/build.sh $SRC/
WORKDIR $SRC/llm-council
