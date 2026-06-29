#include <stdlib.h>
#include <string.h>
#include <VmbC/VmbC.h>

#define EXPORT __declspec(dllexport)
#define NUM_FRAMES 5

static VmbHandle_t g_camera = NULL;
static VmbFrame_t  g_frames[NUM_FRAMES];
static VmbUint32_t g_width = 0;
static VmbUint32_t g_height = 0;
static VmbUint32_t g_payloadSize = 0;
static int g_frameIdx = 0;

EXPORT int Mako_Startup(void) {
    return VmbStartup(NULL);
}

EXPORT int Mako_Shutdown(void) {
    VmbShutdown();
    return 0;
}

EXPORT int Mako_Open(const char* cameraId) {
    return VmbCameraOpen(cameraId, VmbAccessModeFull, &g_camera);
}

EXPORT int Mako_Close(void) {
    VmbError_t err = VmbCameraClose(g_camera);
    g_camera = NULL;
    return err;
}

EXPORT int Mako_Setup(void) {
    VmbError_t err;
    VmbInt64_t w, h;

    VmbFeatureEnumSet(g_camera, "ExposureAuto", "Continuous");
    VmbFeatureEnumSet(g_camera, "BalanceWhiteAuto", "Continuous");
    VmbFeatureEnumSet(g_camera, "PixelFormat", "BayerRG8");

    err = VmbPayloadSizeGet(g_camera, &g_payloadSize);
    if (err != VmbErrorSuccess) return -100;

    err = VmbFeatureIntGet(g_camera, "Width", &w);
    if (err != VmbErrorSuccess) return -101;
    g_width = (VmbUint32_t)w;

    err = VmbFeatureIntGet(g_camera, "Height", &h);
    if (err != VmbErrorSuccess) return -102;
    g_height = (VmbUint32_t)h;

    for (int i = 0; i < NUM_FRAMES; i++) {
        memset(&g_frames[i], 0, sizeof(VmbFrame_t));
        g_frames[i].buffer = malloc(g_payloadSize);
        g_frames[i].bufferSize = g_payloadSize;
        err = VmbFrameAnnounce(g_camera, &g_frames[i], sizeof(VmbFrame_t));
        if (err != VmbErrorSuccess) return -103;
    }

    err = VmbCaptureStart(g_camera);
    if (err != VmbErrorSuccess) return -104;

    for (int i = 0; i < NUM_FRAMES; i++) {
        err = VmbCaptureFrameQueue(g_camera, &g_frames[i], NULL);
        if (err != VmbErrorSuccess) return -105;
    }

    err = VmbFeatureCommandRun(g_camera, "AcquisitionStart");
    if (err != VmbErrorSuccess) return -106;

    g_frameIdx = 0;
    return 0;
}

EXPORT int Mako_GetFrame(unsigned char* outBuffer, unsigned int bufferSize,
                          unsigned int* outWidth, unsigned int* outHeight,
                          unsigned int timeoutMs) {
    VmbFrame_t* pFrame = &g_frames[g_frameIdx];
    g_frameIdx = (g_frameIdx + 1) % NUM_FRAMES;

    VmbError_t err = VmbCaptureFrameWait(g_camera, pFrame, timeoutMs);
    if (err != VmbErrorSuccess) return err;

    if (pFrame->receiveStatus == VmbFrameStatusComplete) {
        unsigned int w = pFrame->width;
        unsigned int h = pFrame->height;
        *outWidth  = w;
        *outHeight = h;

        unsigned char* src = (unsigned char*)pFrame->buffer;

        for (unsigned int y = 0; y < h; y++) {
            for (unsigned int x = 0; x < w; x++) {
                unsigned int idx = y * w + x;
                unsigned int out = idx * 4;
                unsigned char val = src[idx];
                unsigned char r, g, b;

                if (y % 2 == 0 && x % 2 == 0) {
                    r = val;
                    g = (x+1 < w) ? src[idx+1] : val;
                    b = (y+1 < h) ? src[(y+1)*w+x] : val;
                } else if (y % 2 == 0 && x % 2 == 1) {
                    r = (x > 0) ? src[idx-1] : val;
                    g = val;
                    b = (y+1 < h) ? src[(y+1)*w+x] : val;
                } else if (y % 2 == 1 && x % 2 == 0) {
                    r = (y > 0) ? src[(y-1)*w+x] : val;
                    g = val;
                    b = (x+1 < w) ? src[idx+1] : val;
                } else {
                    r = (y > 0 && x > 0) ? src[(y-1)*w+x-1] : val;
                    g = (x > 0) ? src[idx-1] : val;
                    b = val;
                }

                outBuffer[out]   = 255;
                outBuffer[out+1] = r;
                outBuffer[out+2] = g;
                outBuffer[out+3] = b;
            }
        }
    }

    VmbCaptureFrameQueue(g_camera, pFrame, NULL);
    return 0;
}

EXPORT int Mako_Stop(void) {
    VmbFeatureCommandRun(g_camera, "AcquisitionStop");
    VmbCaptureEnd(g_camera);
    VmbCaptureQueueFlush(g_camera);
    VmbFrameRevokeAll(g_camera);
    for (int i = 0; i < NUM_FRAMES; i++) {
        if (g_frames[i].buffer) {
            free(g_frames[i].buffer);
            g_frames[i].buffer = NULL;
        }
    }
    g_frameIdx = 0;
    return 0;
}

EXPORT int Mako_SetExposure(double exposureUs) {
    return VmbFeatureFloatSet(g_camera, "ExposureTimeAbs", exposureUs);
}

EXPORT int Mako_SetGain(double gain) {
    return VmbFeatureFloatSet(g_camera, "Gain", gain);
}
EXPORT int Mako_SetExposureAuto(int autoOn) {
    if (autoOn) {
        return VmbFeatureEnumSet(g_camera, "ExposureAuto", "Continuous");
    } else {
        return VmbFeatureEnumSet(g_camera, "ExposureAuto", "Off");
    }
}
EXPORT int Mako_SetGainAuto(int autoOn) {
    if (autoOn) {
        return VmbFeatureEnumSet(g_camera, "GainAuto", "Continuous");
    } else {
        return VmbFeatureEnumSet(g_camera, "GainAuto", "Off");
    }
}
EXPORT double Mako_GetExposure(void) {
    double value = 0.0;
    VmbFeatureFloatGet(g_camera, "ExposureTimeAbs", &value);
    return value;
}

EXPORT double Mako_GetGain(void) {
    double value = 0.0;
    VmbFeatureFloatGet(g_camera, "Gain", &value);
    return value;
}
EXPORT int Mako_GetWidth(void)  { return (int)g_width; }
EXPORT int Mako_GetHeight(void) { return (int)g_height; }
EXPORT int Mako_GetPayloadSize(void) { return (int)g_payloadSize; }