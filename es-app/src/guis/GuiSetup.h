//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiSetup.h
//
//  The Setup screen (DESIGN.md): a checklist of what's ready, with a progress ring, next to a card of setup
//  tools. Each step runs its tool when chosen, and the checklist is read again afterwards. The checklist comes
//  from the get-started tool (get-started.sh --status).
//

#ifndef ES_APP_GUIS_GUI_SETUP_H
#define ES_APP_GUIS_GUI_SETUP_H

#include "GuiComponent.h"
#include "components/BackgroundComponent.h"
#include "components/ComponentList.h"
#include "components/ImageComponent.h"
#include "components/TextComponent.h"

#include <atomic>
#include <chrono>
#include <mutex>
#include <thread>

class GuiSetup : public GuiComponent
{
public:
    explicit GuiSetup(const std::string& toolsDirectory);
    ~GuiSetup();

    // Starts the checklist read ahead of Setup being picked (called when the menu opens), so the screen
    // opens with it already done or nearly.
    static void prewarm(const std::string& toolsDirectory);

    void update(int deltaTime) override;
    void render(const glm::mat4& parentTrans) override;
    bool input(InputConfig* config, Input input) override;
    std::vector<HelpPrompt> getHelpPrompts() override;

private:
    struct Step {
        std::string key;
        bool done;
        std::string label;
        std::string detail;
        std::vector<std::string> code; // what the detail says, as a code and its values (translated here)
    };

    void layout();
    void readStatus();
    void showStatus();
    void runTool(const std::string& title, const std::string& command);
    void openEmulators();
    void setFocusColumn(int column);
    std::shared_ptr<ComponentList> focusedList() { return mColumn == 0 ? mSteps : mTools; }

    Renderer* mRenderer;
    std::string mToolsDirectory;
    int mGameCount {-1}; // games the checklist found last time (-1: not read yet)
    BackgroundComponent mStepsCard;
    BackgroundComponent mToolsCard;
    ImageComponent mRing;
    TextComponent mCount;
    TextComponent mHeadline;
    TextComponent mSubline;
    TextComponent mToolsTitle;
    std::shared_ptr<ComponentList> mSteps;
    std::shared_ptr<ComponentList> mTools;
    int mColumn;

    // What the background status read shares with this screen. The thread holds its own reference, so leaving the
    // screen never waits for it (the read shells out and can take a second or two): a late result is simply dropped.
    struct Shared {
        std::mutex mutex;
        std::vector<Step> status;
        std::atomic<bool> reading {false};  // a read is running (another isn't started on top of it)
        std::atomic<bool> ready {false};    // a read landed that this screen hasn't shown yet
        std::atomic<bool> hasData {false};  // a read has landed at least once: there is something to show
        std::atomic<long long> finished {0};  // steady clock, ns, of the last landed read (0: none yet)

        // Read just now (started ahead of the screen opening, or moments ago): shown as is, not read again.
        bool fresh() const
        {
            return hasData && std::chrono::steady_clock::now().time_since_epoch().count() - finished <
                              std::chrono::seconds(20).count();
        }
    };
    static void startRead(const std::shared_ptr<Shared>& shared, const std::string& toolsDirectory);

    std::shared_ptr<Shared> mShared;
    static std::shared_ptr<Shared> sStatus;  // the latest read, for the next screen to open on top of
    bool mShown {false};                     // what hasData says was shown on this screen already
};

#endif // ES_APP_GUIS_GUI_SETUP_H
