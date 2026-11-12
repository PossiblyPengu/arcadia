//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiToolRunner.cpp
//

#include "guis/GuiToolRunner.h"

#include "FileData.h"
#include "Log.h"
#include "utils/FileSystemUtil.h"
#include "utils/LocalizationUtil.h"

#include <array>
#include <cstdio>

GuiToolRunner::GuiToolRunner(const std::string& title,
                             const std::string& command,
                             std::function<void()> onClose)
    : mRenderer {Renderer::getInstance()}
    , mGrid {glm::ivec2 {3, 4}}
    , mCommand {command}
    , mOnClose {onClose}
    , mRunning {true}
    , mFinished {false}
{
    addChild(&mBackground);
    addChild(&mGrid);

    mTitle = std::make_shared<TextComponent>(
        Utils::Localization::readable(title), Font::get(FONT_SIZE_LARGE * Utils::Localization::sMenuTitleScaleFactor, FONT_PATH_TITLE),
        mMenuColorTitle, ALIGN_CENTER);
    mGrid.setEntry(mTitle, glm::ivec2 {0, 0}, false, true, glm::ivec2 {3, 1},
                   GridFlags::BORDER_NONE);

    mContainer = std::make_shared<ScrollableContainer>();
    mBody = std::make_shared<TextComponent>("", Font::get(FONT_SIZE_SMALL), mMenuColorPrimary,
                                            ALIGN_LEFT, ALIGN_TOP);
    mContainer->addChild(mBody.get());
    mContainer->setAutoScroll(true); // After the child is added: it resets the child's extent.
    mGrid.setEntry(mContainer, glm::ivec2 {1, 1}, false, true, glm::ivec2 {1, 1},
                   GridFlags::BORDER_NONE, GridFlags::UPDATE_ALWAYS);

    mGrid.setEntry(std::make_shared<GuiComponent>(), glm::ivec2 {0, 2}, false, false,
                   glm::ivec2 {3, 1}, GridFlags::BORDER_NONE);

    std::vector<std::shared_ptr<ButtonComponent>> buttons;
    mCloseButton = std::make_shared<ButtonComponent>(_("CLOSE"), _("close"), [this]() {
        auto onClose = mOnClose;
        delete this;
        if (onClose)
            onClose();
    });
    buttons.push_back(mCloseButton);
    mButtons = MenuComponent::makeButtonGrid(buttons);
    mGrid.setEntry(mButtons, glm::ivec2 {0, 3}, true, false, glm::ivec2 {3, 1},
                   GridFlags::BORDER_TOP);

    const float width {glm::clamp(0.85f * 1.778f / mRenderer->getScreenAspectRatio(), 0.45f, 0.95f) *
                       mRenderer->getScreenWidth()};
    setSize(width, mRenderer->getScreenHeight() * 0.80f);
    setPosition((mRenderer->getScreenWidth() - mSize.x) / 2.0f,
                (mRenderer->getScreenHeight() - mSize.y) / 2.0f);

    mBusyAnim.setSize(mSize);
    mBusyAnim.setText(_("WORKING"));
    mBusyAnim.onSizeChanged();

    mThread = std::make_unique<std::thread>(&GuiToolRunner::run, this);
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

void GuiToolRunner::run()
{
    std::string output;
    const std::string cmd {"ARCADIA_OUTPUT=stdout ARCADIA_HOME=\"" +
                           Utils::FileSystem::getAppDataDirectory() + "\" ARCADIA_ROMS=\"" +
                           FileData::getROMDirectory() + "\" " + mCommand + " 2>&1"};
    if (FILE* pipe = popen(cmd.c_str(), "r")) {
        std::array<char, 512> buffer {};
        while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr)
            output += buffer.data();
        pclose(pipe);
    }
    else {
        output = "The tool couldn't be started.";
    }
    LOG(LogInfo) << "GuiToolRunner: finished \"" << mCommand << "\"";
    {
        std::unique_lock<std::mutex> lock {mMutex};
        mOutput = output;
    }
    mRunning = false;
    mFinished = true;
}

void GuiToolRunner::update(int deltaTime)
{
    if (mRunning) {
        mBusyAnim.update(deltaTime);
    }
    else if (mFinished) {
        std::string text;
        {
            std::unique_lock<std::mutex> lock {mMutex};
            text = mOutput;
        }
        while (!text.empty() && (text.back() == '\n' || text.back() == ' '))
            text.pop_back();
        mBody->setValue(text.empty() ? _("Done.") : text);
        mBody->setSize(mContainer->getSize().x, 0.0f);
        mContainer->resetComponent();
        mFinished = false;
    }
    GuiComponent::update(deltaTime);
}

void GuiToolRunner::render(const glm::mat4& parentTrans)
{
    glm::mat4 trans {parentTrans * getTransform()};
    renderChildren(trans);

    if (mRunning)
        mBusyAnim.render(trans);
}

void GuiToolRunner::onSizeChanged()
{
    mGrid.setRowHeightPerc(0, (mTitle->getFont()->getLetterHeight() * 3.0f) / mSize.y, false);
    mGrid.setRowHeightPerc(2, (mTitle->getFont()->getLetterHeight() * 0.5f) / mSize.y, false);
    mGrid.setRowHeightPerc(3, mButtons->getSize().y / mSize.y);
    mGrid.setColWidthPerc(0, 0.03f);
    mGrid.setColWidthPerc(2, 0.03f);
    mGrid.setSize(mSize);
    mBody->setSize(mContainer->getSize().x, 0.0f);
    mBackground.fitTo(mSize);
}

bool GuiToolRunner::input(InputConfig* config, Input input)
{
    if (mRunning)
        return true; // Nothing to do while it works.

    if (input.value != 0 && (config->isMappedTo("b", input) || config->isMappedTo("back", input))) {
        auto onClose = mOnClose;
        delete this;
        if (onClose)
            onClose();
        return true;
    }
    return GuiComponent::input(config, input);
}

std::vector<HelpPrompt> GuiToolRunner::getHelpPrompts()
{
    if (mRunning)
        return {};
    return {HelpPrompt("a", _("select")), HelpPrompt("b", _("close"))};
}
