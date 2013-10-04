
data MatchTree a = Match (MatchTree a) (MatchTree a) | Winner a

instance Functor MatchTree where
  fmap f (Winner a) = Winner (f a)
  fmap f (Match l r) = Match (fmap f l) (fmap f r)


data Team = Team { name :: [Char] }

playGame :: (Team, Team) -> Team
playGame (Team t1, Team t2) = if (length t1) > (length t2) then (Team t1) else (Team t2)

playNextMatch :: MatchTree Team -> MatchTree Team
playNextMatch (Winner a) = Winner a
playNextMatch (Match l@(Winner a) r@(Winner b)) = Winner (playGame (a, b))
playNextMatch (Match l@(Winner _) r@(Match _ _)) = Match l (playNextMatch r)
playNextMatch (Match l@(Match _ _) r) = Match (playNextMatch l) r

-- runMatches :: MatchTree Team -> Maybe Team
-- runMatches (Match left right) = getWinner (runMatches left) (runMatches right)
--  where
--    getWinner Nothing Nothing = Nothing
--    getWinner l Nothing = l
--    getWinner Nothing r = r
--    getWinner l r = l
-- runMatches maybeWinner = maybeWinner

main :: IO ()
main = putStrLn ""

