#pragma once

#include "CoreMinimal.h"
#include "Async/Future.h"

class FFrameGrabber;
class IImageWriteQueue;

// Captures only this application's viewport. Disk compression runs off the game
// thread. Recording runs are labelled separately from performance benchmarks.
class FSPRideCapture
{
public:
    FSPRideCapture();
    ~FSPRideCapture();
    bool Start();
    void Tick(double Seconds);
    // Keep the present callback until requested frames arrive. Poll on later
    // world ticks so the game thread can render; no additional frames are asked.
    void BeginStop();
    bool PollStop();
    // Immediate teardown fallback. Pending work is reported as incomplete.
    void Stop();
    const FString& GetDirectory() const { return Directory; }
    const FString& GetError() const { return Error; }
    bool Passed() const { return bPassed; }

private:
    struct FWrite
    {
        int32 Index;
        double Seconds;
        FString Filename;
        TFuture<bool> Result;
    };
    void Drain();
    TUniquePtr<FFrameGrabber> Grabber;
    IImageWriteQueue* Queue = nullptr;
    TArray<FWrite> Writes;
    FString Directory, Error;
    FIntRect NativeCaptureRect;
    FIntPoint NativeViewportSize = FIntPoint::ZeroValue;
    FIntPoint NativeWindowSize = FIntPoint::ZeroValue;
    double NextFrame = 0, Duration = 0;
    double CaptureInterval = 1.0 / 8.0;
    double StopStarted = 0;
    int32 Requested = 0, Skipped = 0;
    bool bPassed = false, bStopping = false, bStopTimedOut = false;
};
