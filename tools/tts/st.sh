#!/bin/bash
D=/home/claude/tts/st/sherpa-onnx-supertonic-3-tts-int8-2026-05-11
B=/home/claude/tts/st/sherpa-onnx-v1.13.8-linux-x64-static/bin/sherpa-onnx-offline-tts
$B --supertonic-duration-predictor=$D/duration_predictor.int8.onnx --supertonic-text-encoder=$D/text_encoder.int8.onnx \
 --supertonic-vector-estimator=$D/vector_estimator.int8.onnx --supertonic-vocoder=$D/vocoder.int8.onnx \
 --supertonic-tts-json=$D/tts.json --supertonic-unicode-indexer=$D/unicode_indexer.bin --supertonic-voice-style=$D/voice.bin \
 --lang=ko --num-steps=${5:-10} --speed=${4:-1.0} --sid=$1 --num-threads=8 --output-filename="$3" "$2"
