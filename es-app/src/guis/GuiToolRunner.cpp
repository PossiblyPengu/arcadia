//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiToolRunner.cpp
//

#include "guis/GuiToolRunner.h"

#include "FileData.h"
#include "Log.h"
#include "components/MenuComponent.h"
#include "guis/GuiMsgBox.h"
#include "utils/FileSystemUtil.h"
#include "utils/LocalizationUtil.h"

#include <array>
#include <cstdio>
#include <cstring>
#include <spawn.h>
#include <sstream>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

extern char** environ;

namespace
{
    bool startsWith(const std::string& s, const std::string& prefix) { return s.rfind(prefix, 0) == 0; }

    std::string trimmed(const std::string& s)
    {
        const size_t a {s.find_first_not_of(" \t\r")};
        if (a == std::string::npos)
            return "";
        const size_t b {s.find_last_not_of(" \t\r")};
        return s.substr(a, b - a + 1);
    }

    // The marks tools start their lines with, and what each means.
    const std::vector<std::pair<std::string, std::string>> sMarks {
        {"\u2713", "ok"}, {"\u2717", "fail"}, {"\u2022", "item"}, {"\u25CB", "todo"}, {"\u2192", "hint"}};

    std::string markOf(const std::string& line, std::string& rest)
    {
        for (const auto& [mark, kind] : sMarks) {
            if (startsWith(line, mark)) {
                rest = trimmed(line.substr(mark.size()));
                return kind;
            }
        }
        return "";
    }
} // namespace

GuiToolRunner::GuiToolRunner(const std::string& title,
                             const std::string& command,
                             std::function<void()> onClose)
    : mRenderer {Renderer::getInstance()}
    , mTitleText {Utils::Localization::readable(title)}
    , mCommand {command}
    , mOnClose {onClose}
    , mRunning {false}
    , mFinished {false}
    , mWorked {true}
    , mProgressDone {0}
    , mProgressTotal {0}
    , mSpinTime {0}
    , mSpinFrame {0}
    , mPad {0.0f}
    , mLogTop {0.0f}
    , mLogHeight {0.0f}
    , mContentHeight {0.0f}
    , mScroll {0.0f}
    , mFollow {true}
{
    addChild(&mBackground);
    mTitle.setFont(Font::get(FONT_SIZE_LARGE * 0.78f, FONT_PATH_TITLE));
    mTitle.setColor(mMenuColorTitle);
    mTitle.setText(mTitleText);
    mStatus.setFont(Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT));
    mStatus.setColor(mMenuColorSecondary);
    mDone.setImage(MessageTone::badge("success"));
    mFailed.setImage(MessageTone::badge("warning"));

    mButtons.push_back(std::make_shared<ButtonComponent>(_("WORKING…"), "", [] {}));
    mButtonGrid = MenuComponent::makeButtonGrid(mButtons);
    start();
}

GuiToolRunner::~GuiToolRunner()
{
    // The tool keeps running if the screen is closed early, but its output is no longer wanted.
    if (mThread) {
        if (mRunning)
            mThread->detach();
        else
            mThread->join();
    }
}

void GuiToolRunner::start()
{
    if (mThread && mThread->joinable())
        mThread->join();
    {
        std::unique_lock<std::mutex> lock {mMutex};
        mOutput.clear();
    }
    mWorked = true;
    mProgressDone = mProgressTotal = 0;
    mScroll = 0.0f;
    mFollow = true;
    mFinished = false;
    mRunning = true;
    mChanged = true;
    mStarted = std::chrono::steady_clock::now();
    mBadge.setColorShift(mMenuColorAccent);
    mBadge.setImage(":/graphics/busy_0.svg");
    mStatus.setText("Working on it…");
    // While it works there is one button that does nothing; when it's done, Close (and Try again if it failed).
    mButtons.clear();
    mButtons.push_back(std::make_shared<ButtonComponent>(_("WORKING…"), "", [] {}));
    if (mButtonGrid)
        removeChild(mButtonGrid.get());
    mButtonGrid = MenuComponent::makeButtonGrid(mButtons);
    mButtonGrid->onFocusGained(); // (the first button is the one A presses)
    addChild(mButtonGrid.get());
    rebuild();
    mThread = std::make_unique<std::thread>(&GuiToolRunner::run, this);
}

// Runs a command through sh and collects what it prints (both streams). The command gets Arcadia's environment
// without LD_PRELOAD: started from Steam, Arcadia carries Steam's overlay libraries there (one 32-bit, one 64-bit),
// and every program a tool starts would print "cannot be preloaded (wrong ELF class)" for the one that doesn't fit,
// burying the tool's real output. (Games are launched elsewhere and keep the overlay.)
bool GuiToolRunner::runWithoutPreload(const std::string& cmd,
                                      const std::function<void(const std::string&)>& onOutput,
                                      int* exitCode)
{
    int fds[2];
    if (pipe(fds) != 0)
        return false;

    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, fds[1], STDOUT_FILENO);
    posix_spawn_file_actions_adddup2(&actions, fds[1], STDERR_FILENO);
    posix_spawn_file_actions_addclose(&actions, fds[0]);
    posix_spawn_file_actions_addclose(&actions, fds[1]);

    std::vector<std::string> env;
    for (char** e {environ}; e != nullptr && *e != nullptr; ++e) {
        if (std::strncmp(*e, "LD_PRELOAD=", 11) != 0)
            env.emplace_back(*e);
    }
    std::vector<char*> envp;
    for (std::string& entry : env)
        envp.push_back(entry.data());
    envp.push_back(nullptr);

    char* argv[] {const_cast<char*>("sh"), const_cast<char*>("-c"), const_cast<char*>(cmd.c_str()),
                  nullptr};
    pid_t pid {0};
    const int result {posix_spawn(&pid, "/bin/sh", &actions, nullptr, argv, envp.data())};
    posix_spawn_file_actions_destroy(&actions);
    close(fds[1]);
    if (result != 0) {
        close(fds[0]);
        return false;
    }

    std::array<char, 512> buffer {};
    ssize_t count {0};
    while ((count = read(fds[0], buffer.data(), buffer.size())) > 0)
        onOutput(std::string(buffer.data(), static_cast<size_t>(count)));
    close(fds[0]);
    int status {0};
    waitpid(pid, &status, 0);
    if (exitCode != nullptr)
        *exitCode = WIFEXITED(status) ? WEXITSTATUS(status) : 1;
    return true;
}

std::string GuiToolRunner::toolEnvironment()
{
    return "ARCADIA_OUTPUT=stdout ARCADIA_HOME=\"" + Utils::FileSystem::getAppDataDirectory() +
           "\" ARCADIA_ROMS=\"" + FileData::getROMDirectory() + "\" ";
}

void GuiToolRunner::run()
{
    // What the tool prints is shown as it comes, so a long job (installing emulators) shows where it is.
    int code {0};
    const bool started {runWithoutPreload(
        toolEnvironment() + mCommand,
        [this](const std::string& chunk) {
            std::unique_lock<std::mutex> lock {mMutex};
            mOutput += chunk;
            mChanged = true;
        },
        &code)};
    LOG(LogInfo) << "GuiToolRunner: finished \"" << mCommand << "\" (" << code << ")";
    if (!started) {
        std::unique_lock<std::mutex> lock {mMutex};
        mOutput = "\u2717 The tool couldn't be started.";
    }
    mExitCode = started ? code : 1;
    mRunning = false;
    mFinished = true;
}

std::vector<GuiToolRunner::Line> GuiToolRunner::parse(const std::string& output,
                                                      bool finished,
                                                      int& done,
                                                      int& total)
{
    std::vector<Line> lines;
    std::istringstream in {output};
    std::string raw;
    while (std::getline(in, raw)) {
        const std::string line {trimmed(raw)};
        if (startsWith(line, "@progress ")) {
            int d {0};
            int t {0};
            if (std::sscanf(line.c_str() + 10, "%d/%d", &d, &t) == 2 && t > 0) {
                done = std::clamp(d, 0, t);
                total = t;
            }
            continue;
        }
        if (line.empty()) {
            if (!lines.empty() && lines.back().kind != "gap")
                lines.push_back({"gap", ""});
            continue;
        }
        std::string rest;
        const std::string kind {markOf(line, rest)};
        if (!kind.empty())
            lines.push_back({kind, rest});
        else
            lines.push_back({"text", line});
    }
    while (!lines.empty() && lines.back().kind == "gap")
        lines.pop_back();
    // A short line followed by marked lines, or ending in "…" or ":", is a heading.
    for (size_t i {0}; i < lines.size(); ++i) {
        Line& l {lines[i]};
        if (l.kind != "text" || l.text.size() > 90)
            continue;
        const bool ends {l.text.back() == ':' || (l.text.size() >= 3 && l.text.substr(l.text.size() - 3) == "\u2026")};
        const bool before {i + 1 < lines.size() && lines[i + 1].kind != "text" && lines[i + 1].kind != "gap"};
        if (ends || (before && l.text.size() < 48 && l.text.back() != '.'))
            l.kind = "head";
    }
    // When done, the last paragraph of plain words is the summary.
    if (finished && !lines.empty()) {
        size_t first {lines.size()};
        while (first > 0 && lines[first - 1].kind == "text")
            --first;
        if (first < lines.size() && (first == 0 || lines[first - 1].kind == "gap")) {
            std::string summary;
            for (size_t i {first}; i < lines.size(); ++i)
                summary += (summary.empty() ? "" : "\n") + lines[i].text;
            lines.erase(lines.begin() + static_cast<long>(first), lines.end());
            if (!lines.empty() && lines.back().kind == "gap")
                lines.pop_back();
            lines.push_back({"summary", summary});
        }
    }
    return lines;
}

void GuiToolRunner::rebuild()
{
    std::string output;
    {
        std::unique_lock<std::mutex> lock {mMutex};
        output = mOutput;
        mChanged = false;
    }
    int done {mProgressDone};
    int total {mProgressTotal};
    const std::vector<Line> lines {parse(output, !mRunning, done, total)};
    mProgressDone = done;
    mProgressTotal = total;

    // The card: most of the screen's width; as tall as the lines need, within limits (see layout()).
    const float width {std::round(std::clamp(mRenderer->getScreenWidth() * 0.66f, 480.0f,
                                             mRenderer->getScreenWidth() * 0.92f))};
    mPad = std::round(mRenderer->getScreenWidth() * 0.026f);
    const std::shared_ptr<Font> small {Font::get(FONT_SIZE_SMALL)};
    const std::shared_ptr<Font> bold {Font::get(FONT_SIZE_SMALL, FONT_PATH_BOLD)};
    const std::shared_ptr<Font> big {Font::get(FONT_SIZE_MEDIUM, FONT_PATH_BOLD)};
    const float icon {std::round(small->getLetterHeight() * 1.7f)};
    const float indent {icon + std::round(small->getLetterHeight() * 0.9f)};
    const float spacing {std::round(small->getLetterHeight() * 0.55f)};

    mRows.clear();
    float y {0.0f};
    for (const Line& l : lines) {
        Row row {l.kind, nullptr, y, 0.0f};
        if (l.kind == "gap") {
            row.height = std::round(small->getLetterHeight() * 0.6f);
        }
        else {
            const bool marked {l.kind == "ok" || l.kind == "fail" || l.kind == "item" || l.kind == "todo" ||
                               l.kind == "hint"};
            const float x {marked ? mPad + indent : mPad};
            float room {width - mPad - x};
            std::shared_ptr<Font> font {small};
            unsigned int color {mMenuColorPrimary};
            if (l.kind == "head")
                font = bold;
            else if (l.kind == "hint")
                color = mMenuColorAccentInk;
            else if (l.kind == "text")
                color = mMenuColorSecondary;
            else if (l.kind == "summary") {
                font = big;
                room = width - mPad * 2.0f - small->getLetterHeight() * 2.4f;
                y += spacing;
                row.y = y;
            }
            row.text = std::make_shared<TextComponent>("", font, color, ALIGN_LEFT, ALIGN_TOP);
            row.text->setAutoCalcExtent(glm::ivec2 {0, 1});
            row.text->setSize(room, 0.0f);
            row.text->setText(l.text);
            row.height = std::max(row.text->getSize().y, marked ? icon : 0.0f);
            if (l.kind == "summary") {
                const float boxPad {std::round(small->getLetterHeight() * 1.2f)};
                row.text->setPosition(mPad + boxPad, y + boxPad * 0.8f);
                row.height = row.text->getSize().y + boxPad * 1.6f;
            }
            else {
                row.text->setPosition(x, y + std::max(0.0f, (row.height - row.text->getSize().y) / 2.0f));
            }
        }
        mRows.push_back(row);
        y += row.height + (l.kind == "gap" ? 0.0f : spacing);
    }
    mContentHeight = y;
    setSize(width, mSize.y);
    layout();
}

void GuiToolRunner::layout()
{
    const float screenH {static_cast<float>(mRenderer->getScreenHeight())};
    const float gap {std::round(screenH * 0.02f)};
    const float side {std::round(mTitle.getFont()->getLetterHeight() * 2.3f)};
    mBadge.setResize(side, side);
    mBadge.setPosition(mPad, mPad);
    const float textX {mPad + side + std::round(gap * 1.1f)};
    mTitle.setSize(mSize.x - textX - mPad, 0.0f);
    mTitle.setPosition(textX, mPad + side * 0.5f - mTitle.getFont()->getHeight() * 0.92f);
    mStatus.setSize(mSize.x - textX - mPad, 0.0f);
    mStatus.setPosition(textX, mPad + side * 0.5f + mTitle.getFont()->getHeight() * 0.05f);
    float top {mPad + side + gap};
    if (mProgressTotal > 0)
        top += std::round(screenH * 0.012f) + gap;
    mLogTop = top;
    const float buttons {mButtonGrid->getSize().y + gap * 1.6f};
    const float minH {screenH * 0.44f};
    const float maxH {screenH * 0.86f};
    const float height {std::clamp(top + mContentHeight + gap + buttons, minH, maxH)};
    mLogHeight = height - top - gap - buttons;
    setSize(mSize.x, std::round(height));
    setPosition(std::round((mRenderer->getScreenWidth() - mSize.x) / 2.0f),
                std::round((screenH - mSize.y) / 2.0f));
    mBackground.fitTo(mSize);
    mButtonGrid->setSize(mButtonGrid->getSize());
    mButtonGrid->setPosition(std::round((mSize.x - mButtonGrid->getSize().x) / 2.0f),
                             std::round(mSize.y - buttons + gap * 0.5f));
    if (mFollow)
        mScroll = maxScroll();
    mScroll = std::clamp(mScroll, 0.0f, maxScroll());
}

float GuiToolRunner::maxScroll() const
{
    // (A few pixels over is rounding, not something to scroll to.)
    const float over {mContentHeight - mLogHeight};
    return over > 4.0f ? over : 0.0f;
}

void GuiToolRunner::scrollBy(float amount)
{
    mScroll = std::clamp(mScroll + amount, 0.0f, maxScroll());
    mFollow = mScroll >= maxScroll();
}

void GuiToolRunner::finish()
{
    std::string said;
    {
        std::unique_lock<std::mutex> lock {mMutex};
        said = mOutput;
    }
    // It didn't work if the tool says so: an error exit, a line marked ✗, or a summary that reads like a problem
    // (some tools explain what went wrong and still exit normally). A checklist that lists what's missing is fine.
    int d {0};
    int t {0};
    const std::vector<Line> lines {parse(said, true, d, t)};
    const bool failedLine {std::any_of(lines.cbegin(), lines.cend(), [](const Line& l) { return l.kind == "fail"; })};
    const bool badSummary {!lines.empty() && lines.back().kind == "summary" &&
                           MessageTone::of(lines.back().text) == "warning"};
    mWorked = mExitCode == 0 && !failedLine && !badSummary;
    mBadge.setColorShift(0xFFFFFFFF);
    mBadge.setImage(MessageTone::badge(mWorked ? "success" : "warning"));
    const long seconds {static_cast<long>(std::chrono::duration_cast<std::chrono::seconds>(
                                              std::chrono::steady_clock::now() - mStarted)
                                              .count())};
    const std::string took {seconds < 2   ? "" :
                            seconds < 60  ? " in " + std::to_string(seconds) + " s" :
                                            " in " + std::to_string((seconds + 30) / 60) + " min"};
    mStatus.setText(mWorked ? "Done" + took : "Finished with a problem: see below");
    if (mProgressTotal > 0 && mWorked)
        mProgressDone = mProgressTotal;

    mButtons.clear();
    mButtons.push_back(std::make_shared<ButtonComponent>(_("CLOSE"), _("close"), [this] { closeRunner(); }));
    if (!mWorked)
        mButtons.push_back(std::make_shared<ButtonComponent>(_("TRY AGAIN"), _("try again"), [this] { start(); }));
    removeChild(mButtonGrid.get());
    mButtonGrid = MenuComponent::makeButtonGrid(mButtons);
    mButtonGrid->onFocusGained(); // (the first button is the one A presses)
    addChild(mButtonGrid.get());
    // A quick tool (a report) reads from the top; a long job stays on how it ended.
    mFollow = seconds >= 2;
    if (!mFollow)
        mScroll = 0.0f;
    rebuild();
    updateHelpPrompts();
}

void GuiToolRunner::closeRunner()
{
    auto onClose = mOnClose;
    delete this;
    if (onClose)
        onClose();
}

void GuiToolRunner::update(int deltaTime)
{
    if (mRunning) {
        mSpinTime += deltaTime;
        if (mSpinTime >= 160) {
            mSpinTime = 0;
            mSpinFrame = (mSpinFrame + 1) % 4;
            mBadge.setImage(":/graphics/busy_" + std::to_string(mSpinFrame) + ".svg");
        }
        if (mChanged) {
            rebuild();
            if (mProgressTotal > 0)
                mStatus.setText("Step " + std::to_string(std::min(mProgressDone + 1, mProgressTotal)) + " of " +
                                std::to_string(mProgressTotal) + "… this can take a few minutes");
        }
    }
    else if (mFinished) {
        mFinished = false;
        finish();
    }
    GuiComponent::update(deltaTime);
}

void GuiToolRunner::render(const glm::mat4& parentTrans)
{
    const glm::mat4 trans {parentTrans * getTransform()};
    mBackground.render(trans);
    mBadge.render(trans);
    mTitle.render(trans);
    mStatus.render(trans);

    const float screenH {static_cast<float>(mRenderer->getScreenHeight())};
    if (mProgressTotal > 0) {
        const float barH {std::round(screenH * 0.012f)};
        const float barY {mLogTop - barH - std::round(screenH * 0.02f)};
        const float barW {mSize.x - mPad * 2.0f};
        mRenderer->drawRoundedRect(trans, mPad, barY, barW, barH, mMenuColorTrack, barH / 2.0f);
        const float fill {barW * static_cast<float>(mProgressDone) / static_cast<float>(mProgressTotal)};
        if (fill > 0.0f)
            mRenderer->drawRoundedRect(trans, mPad, barY, std::max(fill, barH), barH,
                                       mWorked ? mMenuColorAccent : 0xF6C08FFF, barH / 2.0f);
    }

    // The lines, clipped to their room and scrolled.
    const glm::ivec2 clipPos {static_cast<int>(trans[3].x), static_cast<int>(trans[3].y + mLogTop)};
    const glm::ivec2 clipDim {static_cast<int>(mSize.x), static_cast<int>(mLogHeight)};
    mRenderer->pushClipRect(clipPos, clipDim);
    const glm::mat4 logTrans {glm::translate(trans, glm::vec3 {0.0f, mLogTop - mScroll, 0.0f})};
    const std::shared_ptr<Font> small {Font::get(FONT_SIZE_SMALL)};
    const float icon {std::round(small->getLetterHeight() * 1.7f)};
    for (Row& row : mRows) {
        if (row.y + row.height < mScroll || row.y > mScroll + mLogHeight)
            continue;
        const float iconY {row.y + std::round((row.height - icon) / 2.0f)};
        if (row.kind == "ok" || row.kind == "fail") {
            ImageComponent& mark {row.kind == "ok" ? mDone : mFailed};
            mark.setResize(icon, icon);
            mark.setPosition(mPad, iconY);
            mark.render(logTrans);
        }
        else if (row.kind == "item" || row.kind == "todo") {
            const float dot {std::round(icon * (row.kind == "item" ? 0.34f : 0.62f))};
            const float x {mPad + (icon - dot) / 2.0f};
            const float y {row.y + (row.height - dot) / 2.0f};
            mRenderer->drawRoundedRect(logTrans, x, y, dot, dot,
                                       row.kind == "item" ? mMenuColorAccentInk : mMenuColorScrollIndicators,
                                       dot / 2.0f);
            if (row.kind == "todo") {
                const float inner {std::round(dot * 0.62f)};
                mRenderer->drawRoundedRect(logTrans, x + (dot - inner) / 2.0f, y + (dot - inner) / 2.0f, inner,
                                           inner, mMenuColorFrame, inner / 2.0f);
            }
        }
        else if (row.kind == "summary") {
            mRenderer->drawRoundedRect(logTrans, mPad, row.y, mSize.x - mPad * 2.0f, row.height,
                                       mWorked ? 0xA8D5A266 : 0xF6C08F77, small->getLetterHeight() * 1.1f);
        }
        if (row.text)
            row.text->render(logTrans);
    }
    mRenderer->popClipRect();
    mRenderer->setMatrix(trans);

    // A fade at the edge that has more above or below it.
    if (mScroll > 1.0f)
        mRenderer->drawRect(0.0f, mLogTop, mSize.x, std::round(screenH * 0.03f), mMenuColorFrame,
                            mMenuColorFrame & 0xFFFFFF00);
    if (mScroll < maxScroll() - 1.0f)
        mRenderer->drawRect(0.0f, mLogTop + mLogHeight - std::round(screenH * 0.03f), mSize.x,
                            std::round(screenH * 0.03f), mMenuColorFrame & 0xFFFFFF00, mMenuColorFrame);

    mButtonGrid->render(trans);
}

bool GuiToolRunner::input(InputConfig* config, Input input)
{
    const float step {Font::get(FONT_SIZE_SMALL)->getHeight() * 3.0f};
    if (input.value != 0 && config->isMappedLike("up", input)) {
        scrollBy(-step);
        return true;
    }
    if (input.value != 0 && config->isMappedLike("down", input)) {
        scrollBy(step);
        return true;
    }
    if (mRunning)
        return true; // Nothing else to do while it works.

    if (input.value != 0 && (config->isMappedTo("b", input) || config->isMappedTo("back", input))) {
        closeRunner();
        return true;
    }
    return mButtonGrid->input(config, input);
}

std::vector<HelpPrompt> GuiToolRunner::getHelpPrompts()
{
    std::vector<HelpPrompt> prompts;
    if (maxScroll() > 0.0f)
        prompts.push_back(HelpPrompt("up/down", _("scroll")));
    if (mRunning)
        return prompts;
    prompts.push_back(HelpPrompt("a", mWorked ? _("close") : _("choose")));
    if (!mWorked)
        prompts.push_back(HelpPrompt("left/right", _("close or try again")));
    prompts.push_back(HelpPrompt("b", _("close")));
    return prompts;
}
