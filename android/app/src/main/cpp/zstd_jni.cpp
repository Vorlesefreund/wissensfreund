#include <jni.h>
#include <android/log.h>
#include <zstd.h>
#include <cstdlib>
#include <cstring>

#define TAG "ZimZstd"

extern "C" JNIEXPORT jbyteArray JNICALL
Java_de_wissensfreund_wissensfreund_1app_ZimZstd_decompress(
        JNIEnv *env, jclass, jbyteArray input) {

    jsize srcLen = env->GetArrayLength(input);
    jbyte *src = env->GetByteArrayElements(input, nullptr);

    unsigned long long frameSize = ZSTD_getFrameContentSize(src, srcLen);

    // Frame header contains known content size — use simple path
    if (frameSize != ZSTD_CONTENTSIZE_UNKNOWN && frameSize != ZSTD_CONTENTSIZE_ERROR) {
        auto *dst = (jbyte *) malloc((size_t) frameSize);
        size_t actual = ZSTD_decompress(dst, (size_t) frameSize, src, (size_t) srcLen);
        env->ReleaseByteArrayElements(input, src, JNI_ABORT);
        if (ZSTD_isError(actual)) {
            __android_log_print(ANDROID_LOG_ERROR, TAG, "decompress: %s", ZSTD_getErrorName(actual));
            free(dst);
            return nullptr;
        }
        jbyteArray result = env->NewByteArray((jsize) actual);
        env->SetByteArrayRegion(result, 0, (jsize) actual, dst);
        free(dst);
        return result;
    }

    // Content size unknown — stream decompress with growing buffer
    ZSTD_DStream *ds = ZSTD_createDStream();
    ZSTD_initDStream(ds);

    size_t outCapacity = (size_t) srcLen * 4;
    if (outCapacity < 65536) outCapacity = 65536;
    auto *outBuf = (jbyte *) malloc(outCapacity);
    size_t outPos = 0;

    ZSTD_inBuffer in = {src, (size_t) srcLen, 0};
    bool error = false;
    while (in.pos < in.size) {
        if (outPos + 65536 > outCapacity) {
            outCapacity *= 2;
            outBuf = (jbyte *) realloc(outBuf, outCapacity);
        }
        ZSTD_outBuffer out = {outBuf + outPos, outCapacity - outPos, 0};
        size_t ret = ZSTD_decompressStream(ds, &out, &in);
        if (ZSTD_isError(ret)) {
            __android_log_print(ANDROID_LOG_ERROR, TAG, "stream decompress: %s", ZSTD_getErrorName(ret));
            error = true;
            break;
        }
        outPos += out.pos;
    }

    env->ReleaseByteArrayElements(input, src, JNI_ABORT);
    ZSTD_freeDStream(ds);

    if (error) {
        free(outBuf);
        return nullptr;
    }

    jbyteArray result = env->NewByteArray((jsize) outPos);
    env->SetByteArrayRegion(result, 0, (jsize) outPos, outBuf);
    free(outBuf);
    return result;
}
