//  SPDX-License-Identifier: MIT
//
//  ES-DE Frontend
//  Log.cpp
//
//  Log output.
//  This class is thread safe.
//

#include "Log.h"
#include "Settings.h"
#include "utils/StringUtil.h"

LogLevel Log::getReportingLevel()
{
    std::unique_lock<std::mutex> lock {sLogMutex};
    return sReportingLevel;
}

void Log::setReportingLevel(LogLevel level)
{
    std::unique_lock<std::mutex> lock {sLogMutex};
    sReportingLevel = level;
}

void Log::init()
{
    sLogPath = Utils::FileSystem::getAppDataDirectory() + "/logs/es_log.txt";

    Utils::FileSystem::removeFile(sLogPath + ".bak");
    // Rename the previous log file.
    Utils::FileSystem::renameFile(sLogPath, sLogPath + ".bak", true);
    return;
}

void Log::open()
{
    std::unique_lock<std::mutex> lock {sLogMutex};
    sFile.open(sLogPath.c_str());
}

void Log::flush()
{
    std::unique_lock<std::mutex> lock {sLogMutex};
    sFile.flush();
}

void Log::close()
{
    std::unique_lock<std::mutex> lock {sLogMutex};
    if (sFile.is_open())
        sFile.close();
}

std::ostringstream& Log::get(LogLevel level)
{
    time_t t {time(nullptr)};
    struct tm tm;
    localtime_r(&t, &tm);
    std::unique_lock<std::mutex> lock {sLogMutex};
    mOutStringStream << std::put_time(&tm, "%b %d %H:%M:%S ") << mLogLevelMap[level]
                     << (level == LogLevel::LogInfo || level == LogLevel::LogWarning ? ":   " :
                                                                                       ":  ");
    mMessageLevel = level;

    return mOutStringStream;
}

Log::~Log()
{
    std::unique_lock<std::mutex> lock {sLogMutex};
    mOutStringStream << std::endl;

    if (!sFile.is_open()) {
        // Not open yet, print to stdout.
        std::cerr << "Error: Tried to write to log file before it was open, "
                     "the following won't be logged:\n";
        std::cerr << mOutStringStream.str();
        return;
    }

    sFile << mOutStringStream.str();

    // If it's an error or the --debug flag has been set, then print to the console as well.
    if (mMessageLevel == LogError || sReportingLevel >= LogDebug)
        std::cerr << mOutStringStream.str();
}
