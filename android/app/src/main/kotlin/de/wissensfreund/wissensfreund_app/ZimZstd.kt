package de.wissensfreund.wissensfreund_app

object ZimZstd {
    init {
        System.loadLibrary("zim_zstd")
    }

    external fun decompress(input: ByteArray): ByteArray?
}
