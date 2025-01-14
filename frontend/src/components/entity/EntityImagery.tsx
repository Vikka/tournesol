import React, { useState } from 'react';
import ReactPlayer from 'react-player/youtube';
import { Box } from '@mui/material';
import { TypeEnum } from 'src/services/openapi';
import { convertDurationToClockDuration } from 'src/utils/video';
import { RelatedEntityObject } from 'src/utils/types';

const PlayerWrapper = React.forwardRef(function PlayerWrapper(
  {
    duration,
    children,
  }: {
    duration?: number;
    children: React.ReactNode;
  },
  ref
) {
  const [isDurationVisible, setIsDurationVisible] = useState(true);
  const formattedDuration: string | null = duration
    ? convertDurationToClockDuration(duration)
    : null;

  return (
    <Box
      position="relative"
      height="100%"
      onClick={() => setIsDurationVisible(false)}
      ref={ref}
    >
      {isDurationVisible && formattedDuration && (
        <Box
          position="absolute"
          bottom={0}
          right={0}
          bgcolor="rgba(0,0,0,0.5)"
          color="#fff"
          px={1}
          fontFamily="system-ui, arial, sans-serif"
          fontSize="0.8em"
          fontWeight="bold"
          sx={{ pointerEvents: 'none' }}
        >
          {formattedDuration}
        </Box>
      )}
      {children}
    </Box>
  );
});

export const VideoPlayer = ({
  videoId,
  duration,
  controls = true,
}: {
  videoId: string;
  duration?: number | null;
  controls?: boolean;
}) => {
  return (
    <ReactPlayer
      url={`https://youtube.com/watch?v=${videoId}`}
      playing
      light
      width="100%"
      height="100%"
      wrapper={PlayerWrapper}
      duration={duration}
      controls={controls}
    />
  );
};

const EntityImagery = ({ entity }: { entity: RelatedEntityObject }) => {
  if (entity.type === TypeEnum.VIDEO) {
    return (
      <VideoPlayer
        videoId={entity.metadata.video_id}
        duration={entity.metadata.duration}
      />
    );
  }
  if (entity.type === TypeEnum.CANDIDATE_FR_2022) {
    return (
      <Box
        display="flex"
        maxHeight="280px"
        justifyContent="center"
        sx={{
          '& img': {
            flex: 1,
            objectFit: 'contain',
          },
        }}
      >
        <img src={entity.metadata.image_url} alt={entity.metadata.name} />
      </Box>
    );
  }
  return null;
};

export default EntityImagery;
