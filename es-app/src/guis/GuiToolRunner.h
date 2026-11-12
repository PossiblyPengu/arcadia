//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiToolRunner.h
//
//  Runs one of the setup tools (a script in the deck folder) and shows what it is doing as it does it: a heading with
//  a spinner (then a tick, or an exclamation mark if something went wrong), the title and how it is going, a progress
//  bar when the tool reports one, and the tool's lines laid out by what they are (done, a problem, a step, a hint),
//  ending with its summary in a tinted box. Used by Setup and its Emulators screen.
//
//  Tools talk to it in plain lines. A line that starts with "✓ " is something done, "✗ " a problem, "• " an item,
//  "○ " something still to do, "→ " a hint; a short line ending in "…" or ":" is a heading; the last paragraph is the
//  summary. "@progress 2/5" (not shown) moves the progress bar.
//

#ifndef ES_APP_GUIS_GUI_TOOL_RUNNER_H
#define ES_APP_GUIS_GUI_TOOL_RUNNER_H

#include "GuiComponent.h"
#include "components/BackgroundComponent.h"
#include "components/ButtonComponent.h"
#include "components/ComponentGrid.h"
#include "components/ImageComponent.h"
#include "components/TextComponent.h"

#include <atomic>
#include <chrono>
#include <functional>
#include <mutex>
#include <thread>

class GuiToolRunner : public GuiComponent
{
public:
    // The command is run through the shell with ARCADIA_OUTPUT=stdout, so the tool prints its message instead of
    // opening a dialog. onClose runs when this screen is closed.
    GuiToolRunner(const std::string& title,
                  const std::string& command,
                  std::function<void()> onClose = nullptr);
    ~GuiToolRunner();

    void update(int deltaTime) override;
    void render(const glm::mat4& parentTrans) override;

    // ARCADIA_OUTPUT=stdout, ARCADIA_HOME and ARCADIA_ROMS, as a prefix for a tool's command.
    static std::string toolEnvironment();
    // Runs a command through sh without Steam's LD_PRELOAD, handing what it prints (both streams) to onOutput as it
    // comes. False if it couldn't be started. exitCode (if given) gets the command's exit status.
    static bool runWithoutPreload(const std::string& cmd,
                                  const std::function<void(const std::string&)>& onOutput,
                                  int* exitCode = nullptr);

    // One line of a tool's output, by what it is (see the top of this file).
    struct Line {
        std::string kind; // head, ok, fail, item, todo, hint, text, gap or summary
        std::string text;
    };
    // The lines of what a tool printed, and its progress (done and total; 0 and 0 when it reports none).
    // finished: the last paragraph becomes the summary.
    static std::vector<Line> parse(const std::string& output, bool finished, int& done, int& total);

private:
    struct Row {
        std::string kind;
        std::shared_ptr<TextComponent> text;
        float y;
        float height;
    };

    void start();
    void run();
    void rebuild();
    void layout();
    void finish();
    void closeRunner();
    void scrollBy(float amount);
    float maxScroll() const;
    bool input(InputConfig* config, Input input) override;
    std::vector<HelpPrompt> getHelpPrompts() override;

    Renderer* mRenderer;
    BackgroundComponent mBackground;
    ImageComponent mBadge; // a spinner while it works; a tick or an exclamation mark when done
    ImageComponent mDone; // the small tick and exclamation mark beside the lines
    ImageComponent mFailed;
    TextComponent mTitle;
    TextComponent mStatus;
    std::vector<Row> mRows;
    std::shared_ptr<ComponentGrid> mButtonGrid;
    std::vector<std::shared_ptr<ButtonComponent>> mButtons;

    std::string mTitleText;
    std::string mCommand;
    std::function<void()> mOnClose;
    std::unique_ptr<std::thread> mThread;
    std::mutex mMutex;
    std::string mOutput;
    std::atomic<bool> mRunning;
    std::atomic<bool> mFinished;
    std::atomic<bool> mChanged {false};
    std::atomic<int> mExitCode {0};
    std::chrono::steady_clock::time_point mStarted;

    bool mWorked;
    int mProgressDone;
    int mProgressTotal;
    int mSpinTime;
    int mSpinFrame;
    float mPad;
    float mLogTop;
    float mLogHeight; // the room the lines have on screen
    float mContentHeight; // how tall all the lines are
    float mScroll;
    bool mFollow; // keep the newest line in view (until scrolled up)
};

#endif // ES_APP_GUIS_GUI_TOOL_RUNNER_H
